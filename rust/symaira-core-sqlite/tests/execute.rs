#![deny(unsafe_code)]

use rusqlite::{ErrorCode, ToSql, types::ToSqlOutput};
use std::{cell::Cell, time::Instant};
use symaira_core_sqlite::{Connection, execute, open};

fn timeout(connection: &Connection) -> i64 {
    connection
        .pragma_query_value(None, "busy_timeout", |row| row.get(0))
        .unwrap()
}

fn rows(connection: &Connection) -> i64 {
    connection
        .query_row("SELECT COUNT(*) FROM probe", [], |row| row.get(0))
        .unwrap()
}

struct CountedValue(Cell<usize>);

impl ToSql for CountedValue {
    fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
        self.0.set(self.0.get() + 1);
        Ok(ToSqlOutput::from(2))
    }
}

#[test]
fn busy_timeout_preserves_policy_and_connection() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("busy.db");
    let mut holder = open(&path).unwrap();
    let mut writer = open(&path).unwrap();
    let reader = open(&path).unwrap();
    holder
        .execute("CREATE TABLE probe(id INTEGER)", [])
        .unwrap();
    let tx = holder.transaction().unwrap();
    tx.execute("INSERT INTO probe VALUES(1)", []).unwrap();
    assert_eq!(timeout(&writer), 5000);

    let value = CountedValue(Cell::new(0));
    let started = Instant::now();
    let error = execute(&mut writer, "INSERT INTO probe VALUES(?)", &[&value]).unwrap_err();
    let seconds = started.elapsed().as_secs_f64();
    eprintln!("SQL-002 busy wait: {seconds:.9}s");
    assert_eq!(error.sqlite_error_code(), Some(ErrorCode::DatabaseBusy));
    assert!((4.5..=6.0).contains(&seconds), "busy wait: {seconds}s");
    assert_eq!(value.0.get(), 1, "retries must retain bound values");
    assert_eq!(timeout(&writer), 5000);
    assert_eq!(rows(&reader), 0, "WAL reader sees no uncommitted write");

    tx.rollback().unwrap();
    assert_eq!(rows(&reader), 0, "timed-out write was not applied");
    assert_eq!(
        execute(
            &mut writer,
            "INSERT INTO probe VALUES(?)",
            rusqlite::params![3]
        )
        .unwrap(),
        1
    );
    assert_eq!(timeout(&writer), 5000);
    assert_eq!(rows(&reader), 1);
}

#[test]
fn released_lock_succeeds_once_without_rebinding() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("released.db");
    let holder = open(&path).unwrap();
    let mut writer = open(&path).unwrap();
    holder
        .execute("CREATE TABLE probe(id INTEGER)", [])
        .unwrap();
    holder
        .execute_batch("BEGIN; INSERT INTO probe VALUES(1)")
        .unwrap();
    let value = CountedValue(Cell::new(0));
    std::thread::scope(|scope| {
        let release = scope.spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(200));
            holder.execute_batch("ROLLBACK").unwrap();
        });
        assert_eq!(
            execute(&mut writer, "INSERT INTO probe VALUES(?)", &[&value]).unwrap(),
            1
        );
        release.join().unwrap();
    });
    assert_eq!(value.0.get(), 1);
    assert_eq!(timeout(&writer), 5000);
    assert_eq!(rows(&writer), 1);
    assert_eq!(
        writer
            .query_row("SELECT id FROM probe", [], |row| row.get::<_, i64>(0))
            .unwrap(),
        2
    );
}

#[test]
fn batches_and_non_busy_errors_are_not_retried() {
    let mut connection = Connection::open_in_memory().unwrap();
    connection
        .execute("CREATE TABLE probe(id INTEGER PRIMARY KEY)", [])
        .unwrap();
    let started = Instant::now();
    assert!(matches!(
        execute(
            &mut connection,
            "INSERT INTO probe VALUES(1); INSERT INTO probe VALUES(2)",
            &[]
        ),
        Err(rusqlite::Error::MultipleStatement)
    ));
    assert_eq!(rows(&connection), 0);
    assert_eq!(timeout(&connection), 5000);
    assert!(matches!(
        execute(&mut connection, "INSERT INTO probe VALUES(?)", &[]),
        Err(rusqlite::Error::InvalidParameterCount(..))
    ));
    assert_eq!(timeout(&connection), 5000);
    execute(&mut connection, "INSERT INTO probe VALUES(1)", &[]).unwrap();
    let error = execute(&mut connection, "INSERT INTO probe VALUES(1)", &[]).unwrap_err();
    assert_eq!(
        error.sqlite_error_code(),
        Some(ErrorCode::ConstraintViolation)
    );
    assert!(started.elapsed().as_secs_f64() < 1.0);
    assert_eq!(timeout(&connection), 5000);
    assert_eq!(rows(&connection), 1);
}

#[test]
fn busy_binding_error_never_executes_incomplete_parameters() {
    struct BusyValue(Cell<usize>);
    impl ToSql for BusyValue {
        fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
            self.0.set(self.0.get() + 1);
            Err(rusqlite::Error::SqliteFailure(
                rusqlite::ffi::Error::new(rusqlite::ffi::SQLITE_BUSY),
                Some("binding failed".into()),
            ))
        }
    }
    let mut connection = Connection::open_in_memory().unwrap();
    connection
        .execute("CREATE TABLE probe(id INTEGER, value TEXT)", [])
        .unwrap();
    let value = BusyValue(Cell::new(0));
    let started = Instant::now();
    let error = execute(
        &mut connection,
        "INSERT INTO probe VALUES(?, ?)",
        &[&1, &value],
    )
    .unwrap_err();
    assert_eq!(error.sqlite_error_code(), Some(ErrorCode::DatabaseBusy));
    assert_eq!(error.to_string(), "binding failed");
    assert!(started.elapsed().as_secs_f64() < 1.0);
    assert_eq!(value.0.get(), 1);
    assert_eq!(rows(&connection), 0);
    assert_eq!(timeout(&connection), 5000);
}

#[test]
fn parameter_panic_restores_timeout() {
    struct Panics;
    impl ToSql for Panics {
        fn to_sql(&self) -> rusqlite::Result<ToSqlOutput<'_>> {
            panic!("parameter conversion failed");
        }
    }
    let mut connection = Connection::open_in_memory().unwrap();
    connection
        .execute("CREATE TABLE probe(id INTEGER)", [])
        .unwrap();
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        let _ = execute(&mut connection, "INSERT INTO probe VALUES(?)", &[&Panics]);
    }));
    assert!(result.is_err());
    assert_eq!(timeout(&connection), 5000);
    assert_eq!(rows(&connection), 0);
    assert_eq!(
        execute(&mut connection, "INSERT INTO probe VALUES(1)", &[]).unwrap(),
        1
    );
}
