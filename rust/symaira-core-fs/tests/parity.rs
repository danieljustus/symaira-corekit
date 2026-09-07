#![deny(unsafe_code)]
#![cfg(not(miri))]

use std::fs;
use symaira_core_fs::{
    FileLock, check_secure_dir, chmod, file_exists, has_traversal, safe_mkdir_all, safe_remove,
    safe_write_file, validate_path, write_file_atomic,
};
use tempfile::tempdir;

#[test]
fn production_corpus_provenance_and_slice_coverage() {
    let corpus = include_str!("../../../testdata/rust-port/fixtures/fs-secret/corpus.json");
    assert!(corpus.contains("f3d3eb79b9b1f31b4f973d2ed518a8292cedf588"));
    for id in [
        "FS-001", "FS-002", "FS-003", "FS-004", "FS-005", "FS-006", "FS-007",
    ] {
        assert!(corpus.contains(id), "missing {id}");
    }
}

#[test]
fn secure_directory_and_exists_semantics() {
    let root = tempdir().expect("tempdir");
    let nested = root.path().join("a/b");
    safe_mkdir_all(&nested, 0o700).expect("mkdir");
    check_secure_dir(&nested).expect("secure");
    let file = nested.join("file");
    fs::write(&file, b"data").expect("file");
    assert!(file_exists(&file).expect("exists"));
    assert!(check_secure_dir(&file).is_err());
    assert!(file_exists(&nested).expect("directory exists"));
    assert!(!file_exists(nested.join("missing")).expect("missing"));
    assert!(validate_path("a/b").is_ok());
    assert!(validate_path("a\\..\\b").is_err());
    #[cfg(windows)]
    assert!(has_traversal("a\\..\\b"));
    #[cfg(not(windows))]
    assert!(!has_traversal("a\\..\\b"));
    safe_remove(&file).expect("remove");
    assert!(!file_exists(&file).expect("removed"));
}

#[test]
fn chmod_and_atomic_rename_failure_are_checked() {
    let root = tempdir().expect("tempdir");
    let mode_file = root.path().join("mode");
    fs::write(&mode_file, b"mode").expect("mode file");
    chmod(&mode_file, 0o600).expect("chmod");
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(
            fs::metadata(&mode_file).expect("mode").permissions().mode() & 0o777,
            0o600
        );
    }
    #[cfg(windows)]
    {
        chmod(&mode_file, 0o444).expect("readonly chmod");
        assert!(
            fs::metadata(&mode_file)
                .expect("readonly")
                .permissions()
                .readonly()
        );
        chmod(&mode_file, 0o600).expect("writable chmod");
        assert!(
            !fs::metadata(&mode_file)
                .expect("writable")
                .permissions()
                .readonly()
        );
    }

    let directory_target = root.path().join("directory-target");
    fs::create_dir(&directory_target).expect("directory target");
    assert!(write_file_atomic(&directory_target, b"blocked", 0o600).is_err());
    assert_eq!(fs::read_dir(root.path()).expect("entries").count(), 2);
}

#[test]
fn safe_write_is_direct_and_rejects_symlink_targets() {
    let root = tempdir().expect("tempdir");
    let file = root.path().join("direct");
    safe_write_file(&file, b"first", 0o600).expect("create");
    safe_write_file(&file, b"second", 0o600).expect("overwrite");
    assert_eq!(fs::read(&file).expect("read"), b"second");
    #[cfg(unix)]
    {
        let outside = root.path().join("outside");
        fs::write(&outside, b"outside").expect("outside");
        let link = root.path().join("link");
        std::os::unix::fs::symlink(&outside, &link).expect("link");
        assert!(safe_write_file(&link, b"blocked", 0o600).is_err());
        assert!(safe_mkdir_all(link.join("child"), 0o700).is_err());
        assert_eq!(fs::read(&outside).expect("outside read"), b"outside");
    }
}

#[test]
fn nonblocking_contention_is_exercised() {
    let root = tempdir().expect("tempdir");
    let lock_path = root.path().join("lock");
    let lock = FileLock::try_lock(&lock_path).expect("first lock");
    assert!(FileLock::try_lock(&lock_path).is_err());
    drop(lock);
    FileLock::try_lock(&lock_path).expect("released");
}
