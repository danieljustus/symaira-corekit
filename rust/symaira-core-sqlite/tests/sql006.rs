#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::{fs, io, path::Path};
use symaira_core_sqlite::{Connection, DirectorySource, Entry, Error, MigrationSource, migrate};

struct Source {
    entries: Vec<(&'static str, &'static str)>,
}

impl MigrationSource for Source {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        Ok(self
            .entries
            .iter()
            .map(|(name, _)| Entry {
                name: (*name).to_owned(),
                is_dir: false,
            })
            .collect())
    }

    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        self.entries
            .iter()
            .find(|(entry, _)| *entry == name)
            .map(|(_, sql)| sql.as_bytes().to_vec())
            .ok_or_else(|| io::Error::from(io::ErrorKind::NotFound))
    }
}

fn migrations() -> Source {
    Source {
        entries: vec![
            (
                "001_test.sql",
                "CREATE TABLE IF NOT EXISTS test_items (\n\tid TEXT PRIMARY KEY,\n\tname TEXT NOT NULL,\n\tcreated_at DATETIME DEFAULT CURRENT_TIMESTAMP\n);",
            ),
            (
                "002_index.sql",
                "CREATE INDEX IF NOT EXISTS idx_test_items_name ON test_items(name);",
            ),
        ],
    }
}

/// Deletes the named migration only after [`DirectorySource`] has listed it.
///
/// This models the real filesystem TOCTOU boundary while preserving
/// `DirectorySource` as the implementation that performs both listing and the
/// eventual failed file read.
struct RemovedMigrationAfterListing<'a> {
    root: &'a Path,
    migration: &'a Path,
}

impl MigrationSource for RemovedMigrationAfterListing<'_> {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        let entries = DirectorySource(self.root).entries()?;
        fs::remove_file(self.migration)?;
        Ok(entries)
    }

    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        DirectorySource(self.root).read(name)
    }
}

fn oracle_sql006() -> Value {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/sqlite/differential-macos-bound-rust006-20260916.json"
    ))
    .expect("source-bound SQLite capture must be valid JSON");
    assert_eq!(fixture["go"]["cases"][5]["id"], "SQL-006");
    fixture["go"]["cases"][5].clone()
}

#[test]
fn in_memory_schema_and_data_match_go_oracle() {
    let oracle = oracle_sql006();
    let mut connection = Connection::open_in_memory().unwrap();
    migrate(&mut connection, &migrations()).unwrap();
    connection
        .execute(
            "INSERT INTO test_items (id, name) VALUES ('memory-1', 'in-memory')",
            [],
        )
        .unwrap();

    let schema = connection
        .prepare(
            "SELECT name, sql, type FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type, name",
        )
        .unwrap()
        .query_map([], |row| {
            Ok(json!({
                "name": row.get::<_, String>(0)?,
                "sql": row.get::<_, String>(1)?,
                "type": row.get::<_, String>(2)?,
            }))
        })
        .unwrap()
        .collect::<Result<Vec<_>, _>>()
        .unwrap();
    let data = connection
        .query_row("SELECT id, name FROM test_items", [], |row| {
            Ok(json!({
                "id": row.get::<_, String>(0)?,
                "name": row.get::<_, String>(1)?,
            }))
        })
        .unwrap();

    assert_eq!(
        json!({"schema": schema, "data": [data]}),
        oracle["state"]["in_memory"]
    );
    assert_eq!(oracle["state"]["in_memory_success"], true);
}

#[test]
fn missing_directory_surfaces_typed_read_directory_error() {
    let oracle = oracle_sql006();
    let mut connection = Connection::open_in_memory().unwrap();
    let root = tempfile::tempdir().unwrap();
    let source = DirectorySource(root.path());

    let error = migrate(&mut connection, &source).unwrap_err();
    let Error::ReadDirectory(cause) = &error else {
        panic!("expected ReadDirectory, got {error:?}");
    };
    assert_eq!(cause.kind(), io::ErrorKind::NotFound);
    assert!(
        error.to_string().starts_with(
            oracle["state"]["missing_dir_error"]
                .as_str()
                .unwrap()
                .split(':')
                .next()
                .unwrap()
        )
    );
}

#[test]
fn version_query_surfaces_sqlite_phase_and_cause() {
    let oracle = oracle_sql006();
    let mut connection = Connection::open_in_memory().unwrap();
    connection
        .execute_batch(
            "CREATE VIEW schema_migrations AS SELECT 1 AS version, datetime('now') AS applied_at FROM missing_table",
        )
        .unwrap();

    let error = migrate(&mut connection, &migrations()).unwrap_err();
    let Error::CheckState { version, source } = &error else {
        panic!("expected CheckState, got {error:?}");
    };
    assert_eq!(version, "001_test");
    assert_eq!(
        source.sqlite_error_code(),
        Some(rusqlite::ErrorCode::Unknown)
    );
    assert_eq!(
        source.sqlite_error().unwrap().code,
        rusqlite::ErrorCode::Unknown
    );
    assert_eq!(source.sqlite_error().unwrap().extended_code & 0xff, 1);
    assert!(
        error.to_string().starts_with(
            oracle["state"]["version_query_error"]
                .as_str()
                .unwrap()
                .split(':')
                .next()
                .unwrap()
        )
    );
}

#[test]
fn migration_file_read_surfaces_typed_error_before_sql_execution() {
    let oracle = oracle_sql006();
    let mut connection = Connection::open_in_memory().unwrap();
    let root = tempfile::tempdir().unwrap();
    let migrations = root.path().join("migrations");
    fs::create_dir(&migrations).unwrap();
    let migration = migrations.join("001_test.sql");
    fs::write(&migration, "CREATE TABLE must_not_run (id INTEGER)").unwrap();
    let source = RemovedMigrationAfterListing {
        root: root.path(),
        migration: &migration,
    };

    let error = migrate(&mut connection, &source).unwrap_err();
    let Error::ReadMigration {
        name,
        source: cause,
    } = &error
    else {
        panic!("expected ReadMigration, got {error:?}");
    };
    assert_eq!(name, "001_test.sql");
    assert_eq!(cause.kind(), io::ErrorKind::NotFound);
    assert!(!migration.exists());
    let created = connection
        .query_row(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'must_not_run'",
            [],
            |row| row.get::<_, i64>(0),
        )
        .unwrap();
    assert_eq!(created, 0, "read failure must not execute migration SQL");
    assert!(
        error.to_string().starts_with(
            oracle["state"]["read_file_error"]
                .as_str()
                .unwrap()
                .split(':')
                .next()
                .unwrap()
        )
    );
}
