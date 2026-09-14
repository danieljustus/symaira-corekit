#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::{cell::Cell, io};
use symaira_core_sqlite::{Connection, Entry, Error, MigrationSource, migrate};

struct Source {
    entries: Vec<(&'static str, &'static str)>,
    fail_directory: bool,
    fail_read: bool,
    reads: Cell<usize>,
}

impl MigrationSource for Source {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        if self.fail_directory {
            return Err(io::Error::from(io::ErrorKind::NotFound));
        }
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
        self.reads.set(self.reads.get() + 1);
        if self.fail_read {
            return Err(io::Error::from(io::ErrorKind::NotFound));
        }
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
        fail_directory: false,
        fail_read: false,
        reads: Cell::new(0),
    }
}

fn oracle_sql006() -> Value {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/sqlite/differential-macos-bound-rust014.json"
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
    let source = Source {
        fail_directory: true,
        ..migrations()
    };

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
    let source = Source {
        fail_read: true,
        ..migrations()
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
    assert_eq!(source.reads.get(), 1);
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
