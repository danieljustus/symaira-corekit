#![deny(unsafe_code)]
//! Domain-free SQLite connection policy and per-file transactional migrations.
//!
//! Every call to [`open`] initializes its own connection. Consumers that maintain
//! pools must use this constructor for **every** pooled connection. No runtime
//! service or product schema is required. Go remains the compatibility oracle.

use std::{
    fs, io,
    path::Path,
    time::{Duration, Instant},
};

pub use rusqlite::Connection;
use thiserror::Error;

/// Errors retain both the migration phase and the underlying provider error.
#[derive(Debug, Error)]
pub enum Error {
    #[error("failed to create database directory: {0}")]
    Directory(#[source] symaira_core_fs::FsError),
    #[error("failed to open sqlite database: {0}")]
    Open(#[source] rusqlite::Error),
    #[error("failed to create schema_migrations table: {0}")]
    CreateTable(#[source] rusqlite::Error),
    #[error("failed to read migrations directory: {0}")]
    ReadDirectory(#[source] io::Error),
    #[error("failed to check migration state for {version}: {source}")]
    CheckState {
        version: String,
        source: rusqlite::Error,
    },
    #[error("failed to read migration {name}: {source}")]
    ReadMigration { name: String, source: io::Error },
    #[error("failed to begin transaction for migration {version}: {source}")]
    Begin {
        version: String,
        source: rusqlite::Error,
    },
    #[error("failed to execute migration {version}: {source}")]
    Execute {
        version: String,
        source: rusqlite::Error,
    },
    #[error("failed to record migration {version}: {source}")]
    Record {
        version: String,
        source: rusqlite::Error,
    },
    #[error("failed to commit migration {version}: {source}")]
    Commit {
        version: String,
        source: rusqlite::Error,
    },
}

/// The busy-wait budget advertised on every connection and enforced around
/// each lock-contended migration statement. See [`retry_locked`].
const BUSY_TIMEOUT: Duration = Duration::from_millis(5000);

/// Open a database with WAL, foreign keys and a five-second busy timeout.
///
/// # Errors
/// Returns directory-creation or eager database/pragma failures.
pub fn open(path: impl AsRef<Path>) -> Result<Connection, Error> {
    let path = path.as_ref();
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    symaira_core_fs::safe_mkdir_all(parent, 0o700).map_err(Error::Directory)?;
    let connection = Connection::open(path).map_err(Error::Open)?;
    connection.busy_timeout(BUSY_TIMEOUT).map_err(Error::Open)?;
    connection
        .pragma_update(None, "foreign_keys", true)
        .map_err(Error::Open)?;
    connection
        .pragma_update(None, "journal_mode", "WAL")
        .map_err(Error::Open)?;
    Ok(connection)
}

/// Execute one statement with a five-second wall-clock busy-wait budget.
///
/// Use this operation boundary for contended writes on connections from [`open`].
/// Raw [`Connection`] methods retain SQLite's nominal busy-sleep schedule, which
/// can exceed five seconds under scheduler latency. Preparation and execution
/// share one retry budget here; positional parameters are bound only once, and
/// only SQLite preparation/step `SQLITE_BUSY` errors are retried. SQL batches are
/// rejected by `prepare`. Pass parameters with `rusqlite::params!` or `&[]`.
///
/// The connection is exclusively borrowed while its native busy handler is
/// temporarily disabled. `PRAGMA busy_timeout` is restored to 5000 before return
/// (including errors and unwinding). This applies the same policy as [`migrate`];
/// it replaces any caller-installed busy handler. The budget bounds lock retries,
/// not SQL execution time or arbitrary parameter conversion work.
///
/// # Errors
/// Returns the original SQLite preparation, binding or execution error, or a
/// busy-timeout configuration error. A timed-out writer retains `SQLITE_BUSY`.
pub fn execute(
    connection: &mut Connection,
    sql: &str,
    params: &[&dyn rusqlite::ToSql],
) -> rusqlite::Result<usize> {
    // retry_locked restores on normal returns. Keep restoration on unwind local
    // to this API, where user-provided ToSql implementations may panic.
    struct RestoreTimeout<'a>(&'a Connection);
    impl Drop for RestoreTimeout<'_> {
        fn drop(&mut self) {
            let _ = self.0.busy_timeout(BUSY_TIMEOUT);
        }
    }
    let _restore = RestoreTimeout(connection);
    let mut statement = None;
    let mut bound = false;
    retry_locked(connection, || {
        if statement.is_none() {
            statement = Some(connection.prepare(sql)?);
        }
        let statement = statement.as_mut().expect("prepared above");
        if !bound {
            if params.len() != statement.parameter_count() {
                return Ok(Err(rusqlite::Error::InvalidParameterCount(
                    params.len(),
                    statement.parameter_count(),
                )));
            }
            for (index, param) in params.iter().enumerate() {
                if let Err(error) = statement.raw_bind_parameter(index + 1, *param) {
                    // A user ToSql can itself return SQLITE_BUSY. Such a binding
                    // error must not retry a statement with incomplete values.
                    return Ok(Err(error));
                }
            }
            bound = true;
        }
        // rusqlite resets after every step, retaining the already-bound values.
        statement.raw_execute().map(Ok)
    })?
}

/// Run `attempt` against `connection`, retrying `SQLITE_BUSY` failures against
/// a wall-clock deadline instead of SQLite's built-in busy handler.
///
/// SQLite's default busy handler tracks a *nominal* elapsed time computed
/// from its fixed retry schedule, not the OS clock: each retry assumes its
/// requested sleep duration elapsed exactly as requested. Under scheduler
/// latency (observed on loaded macOS CI runners), the actual sleeps run
/// noticeably longer than requested, so the nominal schedule reaches its
/// target well before the wall clock does and the real wait overruns the
/// configured timeout by several seconds. Disabling the built-in handler for
/// the duration of the contended statement and retrying against an
/// [`Instant`] deadline keeps the real wait bounded by [`BUSY_TIMEOUT`]
/// regardless of individual sleep overshoot.
fn retry_locked<T>(
    connection: &Connection,
    mut attempt: impl FnMut() -> rusqlite::Result<T>,
) -> rusqlite::Result<T> {
    connection.busy_timeout(Duration::ZERO)?;
    let deadline = Instant::now() + BUSY_TIMEOUT;
    let result = loop {
        match attempt() {
            Err(error)
                if error.sqlite_error_code() == Some(rusqlite::ErrorCode::DatabaseBusy)
                    && Instant::now() < deadline =>
            {
                std::thread::sleep(Duration::from_millis(15));
            }
            other => break other,
        }
    };
    connection.busy_timeout(BUSY_TIMEOUT)?;
    result
}

/// One directory entry in an abstract migration source.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Entry {
    pub name: String,
    pub is_dir: bool,
}

/// Migration filesystem boundary, equivalent to Go's `fs.FS` seam.
///
/// Sources expose the entries under `migrations/`. Contents are loaded only
/// after the migration's recorded version has been checked. Source implementors
/// own their root and entry-name policy; no ambient filesystem access is added.
pub trait MigrationSource {
    /// # Errors
    /// Returns the underlying directory read error.
    fn entries(&self) -> io::Result<Vec<Entry>>;
    /// # Errors
    /// Returns the underlying file read error for an entry from [`Self::entries`].
    fn read(&self, name: &str) -> io::Result<Vec<u8>>;
}

/// An ordinary filesystem root containing a `migrations` directory.
pub struct DirectorySource<'a>(pub &'a Path);

impl MigrationSource for DirectorySource<'_> {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        fs::read_dir(self.0.join("migrations"))?
            .map(|entry| {
                let entry = entry?;
                let name = entry.file_name().into_string().map_err(|_| {
                    io::Error::new(
                        io::ErrorKind::InvalidData,
                        "migration filename is not UTF-8",
                    )
                })?;
                Ok(Entry {
                    name,
                    is_dir: entry.file_type()?.is_dir(),
                })
            })
            .collect()
    }

    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        fs::read(self.0.join("migrations").join(name))
    }
}

// Exact schema SQL from the production Go sqlitekit.Migrate implementation.
const SCHEMA: &str = "CREATE TABLE IF NOT EXISTS schema_migrations (\n\t\tversion TEXT PRIMARY KEY,\n\t\tapplied_at DATETIME DEFAULT CURRENT_TIMESTAMP\n\t)";

/// Apply sorted `.sql` files, atomically recording each successful migration.
/// Earlier successful migrations survive a later failure. Repeated versions
/// are not read or executed again, even if their source has since changed.
///
/// Unlike Go's reusable closed database handle, closing a connection consumes
/// it. The accepted Rust contract rejects use after close at compile time:
///
/// ```compile_fail,E0382
/// use symaira_core_sqlite::{Connection, DirectorySource, migrate};
/// let mut connection = Connection::open_in_memory().unwrap();
/// connection.close().unwrap();
/// let source = DirectorySource(std::path::Path::new("."));
/// migrate(&mut connection, &source).unwrap();
/// ```
///
/// # Errors
/// Returns the failing phase and provider/source error. A failing transaction
/// is rolled back on drop; previously committed migrations are not undone.
pub fn migrate(connection: &mut Connection, source: &impl MigrationSource) -> Result<(), Error> {
    retry_locked(connection, || connection.execute_batch(SCHEMA)).map_err(Error::CreateTable)?;
    let mut entries = source.entries().map_err(Error::ReadDirectory)?;
    entries.retain(|entry| !entry.is_dir && entry.name.ends_with(".sql"));
    entries.sort_by(|a, b| a.name.cmp(&b.name));
    for entry in entries {
        let version = entry.name.strip_suffix(".sql").expect("filtered suffix");
        let count: i64 = connection
            .query_row(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = ?",
                [version],
                |row| row.get(0),
            )
            .map_err(|source| Error::CheckState {
                version: version.into(),
                source,
            })?;
        if count > 0 {
            continue;
        }
        let bytes = source
            .read(&entry.name)
            .map_err(|source| Error::ReadMigration {
                name: entry.name.clone(),
                source,
            })?;
        let sql = std::str::from_utf8(&bytes).map_err(|error| Error::ReadMigration {
            name: entry.name.clone(),
            source: io::Error::new(io::ErrorKind::InvalidData, error),
        })?;
        let transaction = connection.transaction().map_err(|source| Error::Begin {
            version: version.into(),
            source,
        })?;
        retry_locked(&transaction, || transaction.execute_batch(sql)).map_err(|source| {
            Error::Execute {
                version: version.into(),
                source,
            }
        })?;
        transaction
            .execute(
                "INSERT INTO schema_migrations (version) VALUES (?)",
                [version],
            )
            .map_err(|source| Error::Record {
                version: version.into(),
                source,
            })?;
        transaction.commit().map_err(|source| Error::Commit {
            version: version.into(),
            source,
        })?;
    }
    Ok(())
}
