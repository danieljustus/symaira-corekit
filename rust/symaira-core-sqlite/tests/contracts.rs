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
