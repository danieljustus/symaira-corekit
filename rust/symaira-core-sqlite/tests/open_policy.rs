#![deny(unsafe_code)]

#[cfg(unix)]
use std::fs;
use symaira_core_sqlite::{Connection, Error, open, open_with_existing_parent};

fn assert_policy(connection: &Connection) {
    assert_eq!(
        connection
            .pragma_query_value(None, "foreign_keys", |row| row.get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        connection
            .pragma_query_value(None, "busy_timeout", |row| row.get::<_, i64>(0))
            .unwrap(),
        5000
    );
    assert_eq!(
        connection
            .pragma_query_value(None, "journal_mode", |row| row.get::<_, String>(0))
            .unwrap(),
        "wal"
    );
}

#[test]
fn missing_parent_returns_sqlite_open_error_without_creating_directories() {
    let temp = tempfile::tempdir().unwrap();
    let parent = temp.path().join("missing/nested");
    let path = parent.join("db.sqlite");
    let direct_error = Connection::open(&path).unwrap_err();
    let Error::Open(error) = open_with_existing_parent(&path).unwrap_err() else {
        panic!("expected the underlying SQLite open error");
    };
    assert_eq!(error, direct_error);
    assert_eq!(
        error.sqlite_error_code(),
        Some(rusqlite::ErrorCode::CannotOpen)
    );
    assert!(!temp.path().join("missing").exists());
    assert!(!path.exists());
}

#[test]
fn every_existing_parent_connection_receives_policy() {
    let temp = tempfile::tempdir().unwrap();
    let path = temp.path().join("db.sqlite");
    let connections: Vec<_> = (0..3)
        .map(|_| open_with_existing_parent(&path).unwrap())
        .collect();
    for connection in &connections {
        assert_policy(connection);
    }
    assert!(path.is_file());
}

#[cfg(unix)]
#[test]
fn existing_parent_mode_is_preserved() {
    use std::os::unix::fs::PermissionsExt;

    let temp = tempfile::tempdir().unwrap();
    let parent = temp.path().join("legacy");
    fs::create_dir(&parent).unwrap();
    fs::set_permissions(&parent, fs::Permissions::from_mode(0o750)).unwrap();
    let connection = open_with_existing_parent(parent.join("db.sqlite")).unwrap();
    assert_policy(&connection);
    assert_eq!(
        fs::metadata(&parent).unwrap().permissions().mode() & 0o777,
        0o750
    );
}

#[cfg(unix)]
#[test]
fn symlinked_parent_is_preserved_while_secure_open_rejects_it() {
    use std::os::unix::fs::symlink;

    let temp = tempfile::tempdir().unwrap();
    let parent = temp.path().join("legacy");
    let link = temp.path().join("linked");
    fs::create_dir(&parent).unwrap();
    symlink(&parent, &link).unwrap();
    assert!(matches!(
        open(link.join("secure.sqlite")),
        Err(Error::Directory(_))
    ));
    assert!(!parent.join("secure.sqlite").exists());
    let connection = open_with_existing_parent(link.join("db.sqlite")).unwrap();
    assert_policy(&connection);
    assert_eq!(fs::read_link(&link).unwrap(), parent);
    assert!(parent.join("db.sqlite").is_file());
}

#[test]
fn secure_open_still_creates_missing_parents() {
    let temp = tempfile::tempdir().unwrap();
    let parent = temp.path().join("new/nested");
    let path = parent.join("db.sqlite");
    let connection = open(&path).unwrap();
    assert_policy(&connection);
    assert!(path.is_file());
    for directory in [temp.path().join("new"), parent] {
        assert!(directory.is_dir());
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(directory).unwrap().permissions().mode() & 0o777,
                0o700
            );
        }
    }
}
