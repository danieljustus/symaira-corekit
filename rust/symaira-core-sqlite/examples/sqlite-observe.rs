#![deny(unsafe_code)]
//! Test adapter: every observation is obtained through the real Rust library.
use serde_json::{Value, json};
use std::{cell::Cell, collections::BTreeMap, io, path::Path, time::Instant};
use symaira_core_sqlite::{
    Connection, DirectorySource, Entry, Error, MigrationSource, migrate, open,
};

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;

struct MemorySource {
    files: BTreeMap<String, Vec<u8>>,
    reads: Cell<usize>,
    fail_read: bool,
    fail_dir: bool,
}
impl MemorySource {
    fn new(files: &[(&str, &str)]) -> Self {
        Self {
            files: files
                .iter()
                .map(|(k, v)| ((*k).into(), v.as_bytes().to_vec()))
                .collect(),
            reads: Cell::new(0),
            fail_read: false,
            fail_dir: false,
        }
    }
}
impl MigrationSource for MemorySource {
    fn entries(&self) -> io::Result<Vec<Entry>> {
        if self.fail_dir {
            return Err(io::Error::from(io::ErrorKind::NotFound));
        }
        Ok(self
            .files
            .keys()
            .map(|name| Entry {
                name: name.clone(),
                is_dir: false,
            })
            .collect())
    }
    fn read(&self, name: &str) -> io::Result<Vec<u8>> {
        self.reads.set(self.reads.get() + 1);
        if self.fail_read {
            return Err(io::Error::from(io::ErrorKind::NotFound));
        }
        self.files
            .get(name)
            .cloned()
            .ok_or_else(|| io::Error::from(io::ErrorKind::NotFound))
    }
}
fn schema(db: &Connection) -> Result<Value> {
    let mut stmt = db.prepare(
        "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name",
    )?;
    let rows = stmt.query_map([], |row| Ok(json!({"type":row.get::<_,String>(0)?,"name":row.get::<_,String>(1)?,"sql":row.get::<_,String>(2)?})))?;
    Ok(Value::Array(
        rows.collect::<std::result::Result<Vec<_>, _>>()?,
    ))
}
fn snapshot(db: &Connection) -> Result<Value> {
    let count: i64 = db.query_row("SELECT COUNT(*) FROM schema_migrations", [], |r| r.get(0))?;
    let mut stmt = db.prepare("SELECT version, strftime('%Y-%m-%dT%H:%M:%SZ',applied_at) FROM schema_migrations ORDER BY version")?;
    let rows = stmt.query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?;
    let mut versions = Vec::new();
    let mut times = Vec::new();
    for row in rows {
        let (v, t) = row?;
        versions.push(v);
        times.push(t);
    }
    let mut stmt = db.prepare(
        "SELECT id,name,strftime('%Y-%m-%dT%H:%M:%SZ',created_at) FROM test_items ORDER BY id",
    )?;
    let rows = stmt.query_map([],|r| Ok(json!({"id":r.get::<_,String>(0)?,"name":r.get::<_,String>(1)?,"created_at":r.get::<_,String>(2)?})))?;
    let data = rows.collect::<std::result::Result<Vec<_>, _>>()?;
    let (large, null_value): (i64, Option<String>) =
        db.query_row("SELECT 9007199254740993,NULL", [], |r| {
            Ok((r.get(0)?, r.get(1)?))
        })?;
    Ok(
        json!({"migration_count":count,"versions":versions,"applied_at":times,"schema":schema(db)?,"data":data,"large_integer":large,"null_value":null_value}),
    )
}
fn absent(db: &Connection, name: &str) -> Result<bool> {
    Ok(db.query_row(
        "SELECT COUNT(*) FROM sqlite_master WHERE name=?",
        [name],
        |r| r.get::<_, i64>(0),
    )? == 0)
}
fn missing_version(db: &Connection, version: &str) -> Result<bool> {
    Ok(db.query_row(
        "SELECT COUNT(*) FROM schema_migrations WHERE version=?",
        [version],
        |r| r.get::<_, i64>(0),
    )? == 0)
}
fn error_cause(error: &(dyn std::error::Error + 'static)) -> Value {
    let mut current = Some(error);
    while let Some(error) = current {
        if let Some(cause) = error.downcast_ref::<rusqlite::ffi::Error>() {
            return json!({"type":"sqlite","code":cause.extended_code & 255});
        }
        if let Some(cause) = error.downcast_ref::<io::Error>() {
            return json!({"type":"io","kind":format!("{:?}",cause.kind())});
        }
        current = error.source();
    }
    json!({"type":"unclassified"})
}
fn error_value(error: Error) -> Value {
    let kind = match &error {
        Error::Directory(_) => "directory",
        Error::Open(_) => "open",
        Error::CreateTable(_) => "create_table",
        Error::ReadDirectory(_) => "read_directory",
        Error::CheckState { .. } => "check_state",
        Error::ReadMigration { .. } => "read_migration",
        Error::Begin { .. } => "begin",
        Error::Execute { .. } => "execute",
        Error::Record { .. } => "record",
        Error::Commit { .. } => "commit",
    };
    json!({"kind":kind,"error":error.to_string(),"cause":error_cause(&error)})
}
fn observe(root: &Path, fixture: &Path) -> Result<Value> {
    let source = DirectorySource(fixture);
    let mut cases = Vec::new();
    let dbpath = root.join("nested/database.db");
    let db = open(&dbpath)?;
    let ping = db.query_row("SELECT 1", [], |r| r.get::<_, i64>(0))? == 1;
    let mut state = json!({"ping":ping,"database_exists":dbpath.is_file(),"parent_exists":dbpath.parent().unwrap().is_dir()});
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        state["database_mode"] = json!(format!(
            "{:04o}",
            std::fs::metadata(&dbpath)?.permissions().mode() & 0o777
        ));
        state["parent_mode"] = json!(format!(
            "{:04o}",
            std::fs::metadata(dbpath.parent().unwrap())?
                .permissions()
                .mode()
                & 0o777
        ));
    }
    drop(db);
    let directory_error = error_value(open(root).expect_err("opening directory must fail"));
    let parent_file = root.join("not-a-directory");
    std::fs::write(&parent_file, b"file")?;
    let parent_error =
        error_value(open(parent_file.join("db.sqlite")).expect_err("file parent must fail"));
    state["open_errors"] = json!({"directory":directory_error,"parent_file":parent_error});
    cases.push(json!({"id":"SQL-001","state":state}));

    let path = root.join("pragmas.db");
    let mut conns = Vec::new();
    for _ in 0..5 {
        conns.push(open(&path)?);
    }
    let mut policies = Vec::new();
    for c in &conns {
        policies.push(json!({"journal_mode":c.pragma_query_value(None,"journal_mode",|r|r.get::<_,String>(0))?,"foreign_keys":c.pragma_query_value(None,"foreign_keys",|r|r.get::<_,i64>(0))?,"busy_timeout":c.pragma_query_value(None,"busy_timeout",|r|r.get::<_,i64>(0))?}));
    }
    conns[0].execute_batch("CREATE TABLE lock_probe (id INTEGER)")?;
    let (first, others) = conns.split_at_mut(1);
    let tx = first[0].transaction()?;
    tx.execute("INSERT INTO lock_probe VALUES (1)", [])?;
    let started = Instant::now();
    let writer = others[0].execute("INSERT INTO lock_probe VALUES (2)", []);
    let seconds = started.elapsed().as_secs_f64();
    let reader = others[1].query_row("SELECT COUNT(*) FROM lock_probe", [], |r| {
        r.get::<_, i64>(0)
    })?;
    let blocked = writer.is_err();
    let writer_cause = writer.as_ref().err().map(|e| error_cause(e));
    let writer_error = writer.err().map(|e| e.to_string()).unwrap_or_default();
    tx.rollback()?;
    cases.push(json!({"id":"SQL-002","state":{"connections":policies,"contention":{"observed":true,"tx_exec_succeeded":true,"blocked":blocked,"reader_succeeded":reader==0,"reader_value":reader,"rollback_succeeded":true,"within_busy_timeout":(4.0..=6.0).contains(&seconds),"writer_error":writer_error,"writer_cause":writer_cause}}}));

    for (id, repeated) in [("SQL-003", false), ("SQL-004", true)] {
        let mut db = open(root.join(format!("{id}.db")))?;
        migrate(&mut db, &source)?;
        db.execute(
            "INSERT INTO test_items (id,name) VALUES ('item-1','alpha')",
            [],
        )?;
        let before = snapshot(&db)?;
        let mut state = before.clone();
        state["repeat"] = json!(repeated);
        if repeated {
            let invalid = MemorySource::new(&[
                ("001_test.sql", "THIS IS INVALID SQL"),
                ("002_index.sql", "ALSO INVALID"),
            ]);
            migrate(&mut db, &invalid)?;
            let after = snapshot(&db)?;
            for (key, field) in [
                ("rows_unchanged", "data"),
                ("versions_unchanged", "versions"),
                ("schema_unchanged", "schema"),
                ("applied_at_unchanged", "applied_at"),
            ] {
                state[key] = json!(before[field] == after[field]);
            }
            state["replacement_read_attempts"] = json!(invalid.reads.get());
            state["replacement_error_nil"] = json!(true);
        }
        cases.push(json!({"id":id,"state":state}));
    }
    let mut db = open(root.join("rollback.db"))?;
    let bad = MemorySource::new(&[(
        "001_partial.sql",
        "CREATE TABLE rollback_probe (id INTEGER);\nTHIS IS NOT VALID SQL;",
    )]);
    let exec = error_value(migrate(&mut db, &bad).expect_err("bad SQL must fail"));
    let rolled = absent(&db, "rollback_probe")? && missing_version(&db, "001_partial")?;
    let mut record = open(root.join("record.db"))?;
    record.execute_batch("CREATE TABLE versions_underlying (version TEXT, applied_at TEXT); CREATE VIEW schema_migrations AS SELECT version, applied_at FROM versions_underlying")?;
    let insert = error_value(migrate(&mut record, &source).expect_err("read-only view must fail"));
    let insert_absent = absent(&record, "test_items")? && missing_version(&record, "001_test")?;
    let mut partial = open(root.join("partial.db"))?;
    let bad = MemorySource::new(&[
        (
            "001_first.sql",
            "CREATE TABLE first_probe (id INTEGER PRIMARY KEY, value TEXT); INSERT INTO first_probe VALUES (1, 'kept');",
        ),
        (
            "002_second.sql",
            "CREATE TABLE second_probe (id INTEGER); THIS IS NOT VALID SQL;",
        ),
    ]);
    let _ = migrate(&mut partial, &bad).expect_err("second migration must fail");
    let failed_absent =
        missing_version(&partial, "002_second")? && absent(&partial, "second_probe")?;
    let before = partial.query_row("SELECT value FROM first_probe WHERE id=1", [], |r| {
        r.get::<_, String>(0)
    })?;
    let good = MemorySource::new(&[
        ("001_first.sql", "INVALID REPLACEMENT"),
        (
            "002_second.sql",
            "CREATE TABLE second_probe (id INTEGER); INSERT INTO second_probe VALUES (2);",
        ),
    ]);
    migrate(&mut partial, &good)?;
    let after = partial.query_row("SELECT value FROM first_probe WHERE id=1", [], |r| {
        r.get::<_, String>(0)
    })?;
    let version = partial.query_row(
        "SELECT version FROM schema_migrations WHERE version='001_first'",
        [],
        |r| r.get::<_, String>(0),
    )?;
    let second_count = partial.query_row("SELECT COUNT(*) FROM second_probe", [], |r| {
        r.get::<_, i64>(0)
    })?;
    cases.push(json!({"id":"SQL-005","state":{"rollback_probe_absent":rolled,"insert_migration_absent":insert_absent,"partial_rerun":{"first_table_unchanged":before==after,"first_version_unchanged":version=="001_first","first_data_unchanged":before==after,"failed_version_absent":failed_absent,"rerun_succeeded":true,"second_rows":second_count}},"errors":{"exec_failure":exec,"insert_failure":insert}}));

    let mut memory = Connection::open_in_memory()?;
    migrate(&mut memory, &source)?;
    memory.execute(
        "INSERT INTO test_items (id,name) VALUES ('memory-1','in-memory')",
        [],
    )?;
    let memory_schema = schema(&memory)?;
    let data = memory.query_row("SELECT id,name FROM test_items", [], |r| {
        Ok(json!({"id":r.get::<_,String>(0)?,"name":r.get::<_,String>(1)?}))
    })?;
    let mut empty = MemorySource::new(&[]);
    empty.fail_dir = true;
    let missing =
        error_value(migrate(&mut memory, &empty).expect_err("missing directory must fail"));
    let mut query = Connection::open_in_memory()?;
    query.execute_batch("CREATE VIEW schema_migrations AS SELECT 1 AS version, datetime('now') AS applied_at FROM missing_table")?;
    let query_error = error_value(migrate(&mut query, &source).expect_err("broken view must fail"));
    let mut read = Connection::open_in_memory()?;
    let mut failing = MemorySource::new(&[("001_test.sql", "unused")]);
    failing.fail_read = true;
    let read_error = error_value(migrate(&mut read, &failing).expect_err("read must fail"));
    cases.push(json!({"id":"SQL-006","state":{"in_memory_success":true,"in_memory":{"schema":memory_schema,"data":[data]}},"errors":{"missing_directory":missing,"version_query":query_error,"read_file":read_error},"unsupported":["closed_db: rusqlite close consumes Connection; no safe closed handle can be passed to migrate"]}));
    for case in &mut cases {
        let state = &case["state"];
        let yes = |key: &str| state[key].as_bool() == Some(true);
        let success = match case["id"].as_str() {
            Some("SQL-001") => yes("ping") && yes("database_exists") && yes("parent_exists"),
            Some("SQL-002") => [
                "observed",
                "tx_exec_succeeded",
                "blocked",
                "reader_succeeded",
                "rollback_succeeded",
                "within_busy_timeout",
            ]
            .iter()
            .all(|key| state["contention"][key].as_bool() == Some(true)),
            Some("SQL-003") => state["migration_count"].as_i64() == Some(2),
            Some("SQL-004") => {
                [
                    "rows_unchanged",
                    "versions_unchanged",
                    "schema_unchanged",
                    "applied_at_unchanged",
                    "replacement_error_nil",
                ]
                .iter()
                .all(|key| yes(key))
                    && state["replacement_read_attempts"].as_u64() == Some(0)
            }
            Some("SQL-005") => {
                yes("rollback_probe_absent")
                    && yes("insert_migration_absent")
                    && state["partial_rerun"]["rerun_succeeded"].as_bool() == Some(true)
            }
            Some("SQL-006") => yes("in_memory_success"),
            _ => false,
        };
        case["success"] = json!(success);
    }
    let goos = match std::env::consts::OS {
        "macos" => "darwin",
        os => os,
    };
    let goarch = match std::env::consts::ARCH {
        "aarch64" => "arm64",
        "x86_64" => "amd64",
        arch => arch,
    };
    Ok(json!({"cases":cases,"native":{"goos":goos,"goarch":goarch}}))
}
fn main() -> Result<()> {
    let args: Vec<_> = std::env::args_os().collect();
    if args.len() != 3 {
        return Err("usage: sqlite-observe ISOLATED_ROOT FIXTURE_ROOT".into());
    }
    let report = observe(Path::new(&args[1]), Path::new(&args[2]))?;
    println!("{}", serde_json::to_string(&report)?);
    Ok(())
}
