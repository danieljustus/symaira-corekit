#![deny(unsafe_code)]

use rusqlite::{ErrorCode, TransactionBehavior};
use std::{cell::Cell, io, time::Instant};
use symaira_core_sqlite::{Connection, Entry, Error, MigrationSource, migrate, open};

#[derive(Clone, Copy, Debug)]
enum Phase {
    CheckState,
    Begin,
    Record,
    Commit,
}

struct LockedSource {
    holder: Connection,
    phase: Phase,
    locked: Cell<bool>,
    reads: Cell<usize>,
}

impl LockedSource {
    fn lock(&self) {
        if self.locked.replace(true) {
            return;
        }
        self.holder
            .execute_batch(match self.phase {
                Phase::CheckState => "BEGIN EXCLUSIVE",
                Phase::Begin | Phase::Record => "BEGIN IMMEDIATE",
                Phase::Commit => "BEGIN; SELECT * FROM kept",
            })
            .unwrap();
    }
}

impl MigrationSource for LockedSource {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        // Tracking-table creation has finished; an exclusive rollback-journal
        // lock now blocks only the subsequent migration-state query.
        if matches!(self.phase, Phase::CheckState) {
            self.lock();
        }
        Ok(vec![Entry {
            name: "001_probe.sql".into(),
            is_dir: false,
        }])
    }

    fn read(&self, _: &str) -> io::Result<Vec<u8>> {
        self.reads.set(self.reads.get() + 1);
        if !matches!(self.phase, Phase::CheckState) {
            self.lock();
        }
        // TEMP changes are transactional but do not take the main database's
        // writer lock. This makes recording the version the first main write.
        let sql = if matches!(self.phase, Phase::Record) {
            "CREATE TEMP TABLE probe(id INTEGER); INSERT INTO probe VALUES(42)"
        } else {
            "CREATE TABLE probe(id INTEGER); INSERT INTO probe VALUES(42)"
        };
        Ok(sql.as_bytes().to_vec())
    }
}

fn count(connection: &Connection, sql: &str) -> i64 {
    connection.query_row(sql, [], |row| row.get(0)).unwrap()
}

fn assert_preserved(connection: &Connection) {
    assert!(
        connection.is_autocommit(),
        "failed migration kept a transaction"
    );
    assert_eq!(count(connection, "PRAGMA busy_timeout"), 5000);
    assert_eq!(count(connection, "SELECT id FROM kept"), 7);
    assert_eq!(
        count(connection, "SELECT COUNT(*) FROM schema_migrations"),
        1
    );
    assert_eq!(
        count(
            connection,
            "SELECT COUNT(*) FROM schema_migrations WHERE version='000_kept'"
        ),
        1
    );
    for catalog in ["sqlite_master", "sqlite_temp_master"] {
        assert_eq!(
            count(
                connection,
                &format!("SELECT COUNT(*) FROM {catalog} WHERE name='probe'")
            ),
            0,
            "failed migration retained its schema/data"
        );
    }
}

fn contended_migration(phase: Phase) {
    // Real SQLite locks acquired synchronously at the public source boundary;
    // no timed release, injected SQLite errors or replacement migration path.
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("migration.db");
    let mut connection = open(&path).unwrap();
    let baseline = tempfile::tempdir().unwrap();
    std::fs::create_dir(baseline.path().join("migrations")).unwrap();
    std::fs::write(
        baseline.path().join("migrations/000_kept.sql"),
        "CREATE TABLE kept(id INTEGER); INSERT INTO kept VALUES(7)",
    )
    .unwrap();
    migrate(
        &mut connection,
        &symaira_core_sqlite::DirectorySource(baseline.path()),
    )
    .unwrap();
    // WAL readers cannot block state queries or commits. The API accepts a
    // caller-configured connection, so exercise these phases in DELETE mode.
    if matches!(phase, Phase::CheckState | Phase::Commit) {
        connection
            .pragma_update(None, "journal_mode", "DELETE")
            .unwrap();
    }
    if matches!(phase, Phase::Begin) {
        connection.set_transaction_behavior(TransactionBehavior::Immediate);
    }
    let migrations = LockedSource {
        holder: Connection::open(&path).unwrap(),
        phase,
        locked: Cell::new(false),
        reads: Cell::new(0),
    };
    let started = Instant::now();
    let error = migrate(&mut connection, &migrations).unwrap_err();
    let seconds = started.elapsed().as_secs_f64();
    eprintln!("migration {phase:?} busy wait: {seconds:.9}s; error: {error}");
    let (version, cause) = match (&phase, &error) {
        (Phase::CheckState, Error::CheckState { version, source })
        | (Phase::Begin, Error::Begin { version, source })
        | (Phase::Record, Error::Record { version, source })
        | (Phase::Commit, Error::Commit { version, source }) => (version, source),
        _ => panic!("wrong migration phase: {error:?}"),
    };
    assert_eq!(version, "001_probe");
    assert_eq!(cause.sqlite_error_code(), Some(ErrorCode::DatabaseBusy));
    assert_eq!(
        std::error::Error::source(&error)
            .unwrap()
            .downcast_ref::<rusqlite::Error>(),
        Some(cause)
    );
    assert!(connection.is_autocommit());
    assert_eq!(count(&connection, "PRAGMA busy_timeout"), 5000);
    assert_eq!(
        migrations.reads.get(),
        usize::from(!matches!(phase, Phase::CheckState))
    );
    // Inspect through the lock holder before release: the failed commit/record
    // must not expose a new version or disturb the prior successful migration.
    assert_eq!(count(&migrations.holder, "SELECT id FROM kept"), 7);
    assert_eq!(
        count(&migrations.holder, "SELECT COUNT(*) FROM schema_migrations"),
        1
    );
    migrations.holder.execute_batch("ROLLBACK").unwrap();
    assert_preserved(&connection);

    // The source's one-shot lock remains released. A new migration succeeds,
    // committing exactly one copy of its data and version; rerunning skips it.
    migrate(&mut connection, &migrations).unwrap();
    let reads = migrations.reads.get();
    migrate(&mut connection, &migrations).unwrap();
    assert_eq!(migrations.reads.get(), reads);
    assert!(connection.is_autocommit());
    assert_eq!(count(&connection, "PRAGMA busy_timeout"), 5000);
    assert_eq!(
        count(&connection, "SELECT COUNT(*) FROM schema_migrations"),
        2
    );
    assert_eq!(count(&connection, "SELECT COUNT(*) FROM probe"), 1);
    assert_eq!(count(&connection, "SELECT id FROM probe"), 42);
    assert_eq!(count(&connection, "SELECT id FROM kept"), 7);
    // Keep the same native wall-clock gate as the existing locked migrations.
    assert!(
        (4.5..=6.0).contains(&seconds),
        "{phase:?} busy wait: {seconds}s"
    );
}

#[test]
fn check_state_busy_is_bounded_and_preserves_state() {
    contended_migration(Phase::CheckState);
}

#[test]
fn begin_busy_is_bounded_and_preserves_state() {
    contended_migration(Phase::Begin);
}

#[test]
fn record_busy_is_bounded_and_rolls_back() {
    contended_migration(Phase::Record);
}

#[test]
fn commit_busy_is_bounded_and_rolls_back() {
    contended_migration(Phase::Commit);
}
