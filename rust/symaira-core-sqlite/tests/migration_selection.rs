#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::{cell::RefCell, io};
use symaira_core_sqlite::{Connection, Entry, MigrationSource, migrate};

struct Source<'a> {
    entries: &'a [Value],
    reads: RefCell<Vec<String>>,
}

impl MigrationSource for Source<'_> {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        Ok(self
            .entries
            .iter()
            .map(|entry| Entry {
                name: entry["name"].as_str().unwrap().into(),
                is_dir: entry["is_dir"].as_bool().unwrap(),
            })
            .collect())
    }

    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        self.reads.borrow_mut().push(format!("migrations/{name}"));
        self.entries
            .iter()
            .find(|entry| entry["name"] == name)
            .map(|entry| entry["sql"].as_str().unwrap().as_bytes().to_vec())
            .ok_or_else(|| io::Error::from(io::ErrorKind::NotFound))
    }
}

#[test]
fn migration_selection_matches_pinned_go() {
    let input: Value = serde_json::from_str(include_str!(
        "../../../scripts/rust-port/sqlite/testdata/migration-selection/cases.json"
    ))
    .unwrap();
    let expected: Value = serde_json::from_str(include_str!(
        "../../../scripts/rust-port/sqlite/testdata/migration-selection/observed.json"
    ))
    .unwrap();
    assert_eq!(input["case_ids"], json!(["SQL-003/migration-selection"]));
    assert_eq!(expected["case_ids"], input["case_ids"]);
    assert_eq!(
        expected["oracle_commit"],
        "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"
    );
    let mut actual = Vec::new();
    for case in input["cases"].as_array().unwrap() {
        let source = Source {
            entries: case["entries"].as_array().unwrap(),
            reads: RefCell::new(Vec::new()),
        };
        let mut connection = Connection::open_in_memory().unwrap();
        migrate(&mut connection, &source).unwrap();
        let versions = connection
            .prepare("SELECT version FROM schema_migrations ORDER BY version")
            .unwrap()
            .query_map([], |row| row.get::<_, String>(0))
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        let schema = connection
            .prepare("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")
            .unwrap()
            .query_map([], |row| {
                Ok(json!({"type": row.get::<_, String>(0)?, "name": row.get::<_, String>(1)?, "sql": row.get::<_, String>(2)?}))
            })
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        let data = connection
            .prepare("SELECT id,value FROM selection ORDER BY id")
            .unwrap()
            .query_map([], |row| {
                Ok(json!({"id": row.get::<_, i64>(0)?, "value": row.get::<_, String>(1)?}))
            })
            .unwrap()
            .collect::<Result<Vec<_>, _>>()
            .unwrap();
        actual.push(json!({"id": case["id"], "reads": source.reads.into_inner(),
                           "versions": versions, "schema": schema, "data": data}));
    }
    let executed: Vec<_> = actual.iter().map(|case| case["id"].clone()).collect();
    assert_eq!(json!(executed), input["case_ids"]);
    // SQLite schema strings, ordered rows/versions and read trace compare
    // exactly. JSON object formatting is insignificant; no fields normalize.
    assert_eq!(json!(actual), expected["cases"]);
    eprintln!("executed_case_ids={}", json!(executed));
}
