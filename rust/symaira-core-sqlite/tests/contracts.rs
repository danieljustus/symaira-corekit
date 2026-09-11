#![deny(unsafe_code)]
use std::{cell::Cell, io};
use symaira_core_sqlite::{Connection, Entry, Error, MigrationSource, migrate, open};

struct Source<'a> {
    files: Vec<(&'a str, &'a str)>,
    reads: Cell<usize>,
}
impl MigrationSource for Source<'_> {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        Ok(self
            .files
            .iter()
            .map(|(name, _)| Entry {
                name: (*name).into(),
                is_dir: false,
            })
            .collect())
    }
    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        self.reads.set(self.reads.get() + 1);
        self.files
            .iter()
            .find(|(n, _)| *n == name)
            .map(|(_, sql)| sql.as_bytes().to_vec())
            .ok_or_else(|| io::Error::from(io::ErrorKind::NotFound))
    }
}
fn source<'a>(files: Vec<(&'a str, &'a str)>) -> Source<'a> {
    Source {
        files,
        reads: Cell::new(0),
    }
}

#[test]
fn every_connection_receives_policy_and_special_path_opens() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("with space/db.sqlite");
    let connections: Vec<_> = (0..5).map(|_| open(&path).unwrap()).collect();
    for connection in &connections {
        assert_eq!(
            connection
                .pragma_query_value(None, "foreign_keys", |r| r.get::<_, i64>(0))
                .unwrap(),
            1
        );
        assert_eq!(
            connection
                .pragma_query_value(None, "busy_timeout", |r| r.get::<_, i64>(0))
                .unwrap(),
            5000
        );
        assert_eq!(
            connection
                .pragma_query_value(None, "journal_mode", |r| r.get::<_, String>(0))
                .unwrap(),
            "wal"
        );
    }
    assert!(path.is_file());
    assert!(matches!(open(temp.path()), Err(Error::Open(_))));
}

#[test]
fn migrations_sort_and_skip_applied_bytes_without_reading() {
    let mut connection = Connection::open_in_memory().unwrap();
    let initial = source(vec![
        (
            "002_add.sql",
            "INSERT INTO items VALUES(9007199254740993,NULL)",
        ),
        (
            "001_create.sql",
            "CREATE TABLE items(id INTEGER,value TEXT)",
        ),
        ("ignored.txt", "INVALID"),
    ]);
    migrate(&mut connection, &initial).unwrap();
    let replacement = source(vec![
        ("001_create.sql", "INVALID"),
        ("002_add.sql", "INVALID"),
    ]);
    migrate(&mut connection, &replacement).unwrap();
    assert_eq!(replacement.reads.get(), 0);
    let row: (i64, Option<String>) = connection
        .query_row("SELECT id,value FROM items", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })
        .unwrap();
    assert_eq!(row, (9007199254740993, None));
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM items", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
}

#[test]
fn failed_migration_rolls_back_both_schema_and_version() {
    let mut connection = Connection::open_in_memory().unwrap();
    let migrations = source(vec![
        ("001_ok.sql", "CREATE TABLE kept(id INTEGER)"),
        (
            "002_bad.sql",
            "CREATE TABLE rolled_back(id INTEGER); INVALID SQL",
        ),
    ]);
    assert!(matches!(
        migrate(&mut connection, &migrations),
        Err(Error::Execute { .. })
    ));
    assert_eq!(
        connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='rolled_back'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
        0
    );
    assert_eq!(
        connection
            .query_row("SELECT version FROM schema_migrations", [], |r| r
                .get::<_, String>(0))
            .unwrap(),
        "001_ok"
    );
    assert!(matches!(
        migrate(&mut connection, &migrations),
        Err(Error::Execute { .. })
    ));
    assert_eq!(
        connection
            .query_row("SELECT COUNT(*) FROM schema_migrations", [], |r| r
                .get::<_, i64>(0))
            .unwrap(),
        1
    );
}

#[test]
fn record_failure_rolls_back_executed_schema() {
    let mut connection = Connection::open_in_memory().unwrap();
    connection.execute_batch("CREATE TABLE underlying(version TEXT); CREATE VIEW schema_migrations AS SELECT version FROM underlying").unwrap();
    let migrations = source(vec![("001_create.sql", "CREATE TABLE probe(id INTEGER)")]);
    let error = migrate(&mut connection, &migrations).unwrap_err();
    assert!(matches!(error, Error::Record { .. }));
    assert!(std::error::Error::source(&error).is_some());
    assert_eq!(
        connection
            .query_row(
                "SELECT COUNT(*) FROM sqlite_master WHERE name='probe'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
        0
    );
}

#[test]
fn read_directory_and_query_errors_preserve_phase() {
    let mut connection = Connection::open_in_memory().unwrap();
    let temp = tempfile::tempdir().unwrap();
    assert!(matches!(
        migrate(
            &mut connection,
            &symaira_core_sqlite::DirectorySource(temp.path())
        ),
        Err(Error::ReadDirectory(_))
    ));
    let mut broken = Connection::open_in_memory().unwrap();
    broken
        .execute_batch("CREATE VIEW schema_migrations AS SELECT version FROM missing_table")
        .unwrap();
    assert!(matches!(
        migrate(&mut broken, &source(vec![("001.sql", "SELECT 1")])),
        Err(Error::CheckState { .. })
    ));
}

#[test]
fn locked_migrations_match_go_timeout_and_error_phases() {
    use serde_json::{Value, json};
    use std::time::{Duration, Instant};

    fn count(connection: &Connection, sql: &str) -> i64 {
        connection.query_row(sql, [], |r| r.get(0)).unwrap()
    }

    // Observe the production sequence without replacing SQLite's busy handler
    // or splitting Migrate into a test implementation. A missing entries/read
    // checkpoint identifies a wait in tracking-table creation; a completed read
    // plus Error::Execute identifies the single CREATE TABLE migration below.
    struct ObservedSource<'a> {
        inner: Source<'a>,
        started: Instant,
        entries_seconds: Cell<Option<f64>>,
        read_seconds: Cell<Option<f64>>,
    }
    impl MigrationSource for ObservedSource<'_> {
        fn entries(&self) -> io::Result<Vec<Entry>> {
            self.entries_seconds
                .set(Some(self.started.elapsed().as_secs_f64()));
            self.inner.entries()
        }

        fn read(&self, name: &str) -> io::Result<Vec<u8>> {
            let result = self.inner.read(name);
            self.read_seconds
                .set(Some(self.started.elapsed().as_secs_f64()));
            result
        }
    }

    // Generated by the source-bound Go helper, not inferred from Rust errors.
    // Preserve contentionCase's sequence: acquire a real SQLite writer lock,
    // compete synchronously, read through WAL, then explicitly roll back.
    // There is no child lock holder or sleep-based release race in that oracle.
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../scripts/rust-port/sqlite/testdata/locked-migration/observed.json"
    ))
    .unwrap();
    let cases = fixture["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 2);
    let mut waits = Vec::new();
    let mut cleanups = Vec::new();
    for (case, precreated) in cases.iter().zip([false, true]) {
        // Explicit internal scratch root; never put a database in Cargo's
        // externally stored target directory or use an ambient user database.
        let temp = tempfile::Builder::new()
            .prefix("locked-migration-")
            .tempdir()
            .unwrap();
        let path = temp.path().join("database.db");
        let mut holder = open(&path).unwrap();
        let reader = open(&path).unwrap();
        let mut contender = open(&path).unwrap();
        let policies: Vec<_> = [&holder, &reader, &contender]
            .into_iter()
            .map(|c| {
                json!({
                    "busy_timeout": count(c, "PRAGMA busy_timeout"),
                    "foreign_keys": count(c, "PRAGMA foreign_keys"),
                    "journal_mode": c.pragma_query_value(None, "journal_mode", |r| r.get::<_, String>(0)).unwrap()
                })
            })
            .collect();
        assert!(path.is_file());
        contender
            .execute_batch("CREATE TABLE lock_probe (id INTEGER)")
            .unwrap();
        if precreated {
            migrate(&mut contender, &source(vec![])).unwrap();
        }
        let migrations = source(vec![(
            "001_probe.sql",
            "CREATE TABLE migration_probe (id INTEGER)",
        )]);
        let tx = holder.transaction().unwrap();
        tx.execute("INSERT INTO lock_probe VALUES (1)", []).unwrap();
        let started = Instant::now();
        let migrations = ObservedSource {
            inner: migrations,
            started,
            entries_seconds: Cell::new(None),
            read_seconds: Cell::new(None),
        };
        let error = migrate(&mut contender, &migrations).unwrap_err();
        let busy_seconds = started.elapsed().as_secs_f64();
        waits.push(busy_seconds);
        // Emit before validating phase/state so failures retain the actual wait.
        // These are diagnostic observations, not a waiver of the timing gate.
        eprintln!(
            "locked migration operation: {}",
            json!({
                "manifest_dir": env!("CARGO_MANIFEST_DIR"),
                "os": std::env::consts::OS,
                "arch": std::env::consts::ARCH,
                "sqlite_version": rusqlite::version(),
                "schema_precreated": precreated,
                "busy_seconds": busy_seconds,
                "entries_seconds": migrations.entries_seconds.get(),
                "read_seconds": migrations.read_seconds.get(),
                "error": error.to_string(),
                "autocommit": contender.is_autocommit(),
            })
        );
        let (phase, cause) = match &error {
            Error::CreateTable(cause) if !precreated => ("create_table", cause),
            Error::Execute { version, source } if precreated => {
                assert_eq!(version, "001_probe");
                ("execute", source)
            }
            other => panic!("wrong locked migration phase: {other:?}"),
        };
        let chained = std::error::Error::source(&error)
            .unwrap()
            .downcast_ref::<rusqlite::Error>()
            .unwrap();
        assert_eq!(chained, cause);
        let code = cause.sqlite_error().unwrap();
        assert_eq!(code.code, rusqlite::ErrorCode::DatabaseBusy);
        assert_eq!(migrations.entries_seconds.get().is_some(), precreated);
        assert_eq!(migrations.read_seconds.get().is_some(), precreated);
        assert_eq!(migrations.inner.reads.get(), usize::from(precreated));
        let reader_value = count(&reader, "SELECT COUNT(*) FROM lock_probe");
        let probe_absent = count(
            &contender,
            "SELECT COUNT(*) FROM sqlite_master WHERE name='migration_probe'",
        ) == 0;
        let tracking_exists = count(
            &contender,
            "SELECT COUNT(*) FROM sqlite_master WHERE name='schema_migrations'",
        ) == 1;
        let version_absent =
            !tracking_exists || count(&contender, "SELECT COUNT(*) FROM schema_migrations") == 0;
        assert!(
            contender.is_autocommit(),
            "failed migration retained a transaction"
        );
        let cleanup = Instant::now();
        tx.rollback().unwrap();
        let rollback_duration = cleanup.elapsed();
        cleanups.push(rollback_duration);
        // Successful reuse proves neither failed migration nor holder kept a
        // lock or recorded a version. A new write must survive the rollback.
        migrate(&mut contender, &migrations).unwrap();
        contender
            .execute("INSERT INTO lock_probe VALUES (2)", [])
            .unwrap();
        let state = json!({
            "schema_precreated": precreated,
            "connections": policies,
            "error": {"phase": phase, "sqlite_primary_code": code.extended_code & 255},
            "reader_value": reader_value, "probe_absent": probe_absent,
            "tracking_exists": tracking_exists, "version_absent": version_absent,
            "retry_version_count": count(&contender, "SELECT COUNT(*) FROM schema_migrations WHERE version='001_probe'"),
            "retry_probe_count": count(&contender, "SELECT COUNT(*) FROM sqlite_master WHERE name='migration_probe'"),
            "released_writer_value": count(&contender, "SELECT id FROM lock_probe")
        });
        let cleanup = Instant::now();
        contender.close().unwrap();
        reader.close().unwrap();
        holder.close().unwrap();
        temp.close().unwrap();
        let close_duration = cleanup.elapsed();
        cleanups.push(close_duration);
        eprintln!(
            "locked migration state: {}",
            json!({
                "phase": phase,
                "state": state,
                "go_state_matched": state == case["state"],
                "rollback_seconds": rollback_duration.as_secs_f64(),
                "close_seconds": close_duration.as_secs_f64(),
            })
        );
        assert_eq!(state, case["state"]);
    }
    // Check both waits after releasing all connections so a timing failure
    // still reports both phases and verifies cleanup, without relaxing bounds.
    // Native macOS has exceeded this bound with matching state; the cause is
    // unresolved. Keep this regression failing until the contract is satisfied.
    assert!(
        cleanups
            .iter()
            .all(|elapsed| *elapsed <= Duration::from_secs(1)),
        "locked migration cleanup exceeded one second: {cleanups:?}"
    );
    assert!(
        waits.iter().all(|seconds| (4.5..=6.0).contains(seconds)),
        "locked migrations exceeded the declared busy timeout: {waits:?}"
    );
}
