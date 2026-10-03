#[path = "common/static_update.rs"]
mod static_update;

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::path::PathBuf;
use symaira_core_update::extract::{extract_binary_to_dir, observe};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<ExpectedCase>,
}

#[derive(Deserialize)]
struct ExpectedCase {
    id: String,
    kind: String,
    archive: String,
    expected_binary: String,
    #[serde(default)]
    selected_binary: String,
    #[serde(default)]
    input_archive_path: String,
    #[serde(default)]
    input_archive_sha256: String,
    files: Vec<ExpectedFile>,
    error: Option<ExpectedError>,
}

#[derive(Deserialize)]
struct ExpectedFile {
    path: String,
    content: String,
    #[allow(dead_code)] // mode parity is asserted on unix only
    mode: u32,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
struct ExpectedError {
    code: String,
    message: String,
}

#[test]
fn extraction_matches_go_archives_and_filesystem_observations() {
    let default_fixture = static_update::fixture_path("extract");
    let fixture_path = std::env::var_os("EXTRACT_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_str(
        &std::fs::read_to_string(&fixture_path).expect("read generated extraction fixture"),
    )
    .expect("valid generated extraction fixture");
    assert_eq!(fixture.cases.len(), 12);
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    for expected in fixture.cases {
        let archive_path = if expected.input_archive_path.is_empty() {
            root.join(&expected.archive)
        } else {
            root.join(&expected.input_archive_path)
        };
        let archive = std::fs::read(archive_path)
            .unwrap_or_else(|err| panic!("{} archive: {err}", expected.id));
        if !expected.input_archive_sha256.is_empty() {
            let actual_sha256 = Sha256::digest(&archive)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect::<String>();
            assert_eq!(
                actual_sha256, expected.input_archive_sha256,
                "{} input archive SHA-256",
                expected.id
            );
        }
        let actual = observe(&expected.kind, &archive, &expected.expected_binary);
        assert_eq!(
            actual
                .error
                .as_ref()
                .map(|error| (&error.code, &error.message)),
            expected
                .error
                .as_ref()
                .map(|error| (&error.code, &error.message)),
            "{} error",
            expected.id
        );
        assert_eq!(
            actual.selected_binary, expected.selected_binary,
            "{} binary",
            expected.id
        );
        assert_eq!(
            actual.files.len(),
            expected.files.len(),
            "{} file count",
            expected.id
        );
        for (actual_file, expected_file) in actual.files.iter().zip(&expected.files) {
            assert_eq!(
                actual_file.path, expected_file.path,
                "{} paths",
                expected.id
            );
            assert_eq!(
                actual_file.content, expected_file.content,
                "{} content",
                expected.id
            );
            #[cfg(unix)]
            assert_eq!(actual_file.mode, expected_file.mode, "{} mode", expected.id);
        }
    }
}

#[test]
fn production_extraction_keeps_binary_in_staging_and_rejects_traversal() {
    let fixture: Fixture = serde_json::from_str(
        &std::fs::read_to_string(
            PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../testdata/rust-port/fixtures/update/extract.json"),
        )
        .unwrap(),
    )
    .unwrap();
    let archive_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let root = std::env::temp_dir().join(format!(
        "symaira-update-extract-install-{}",
        std::process::id()
    ));
    std::fs::create_dir(&root).unwrap();
    std::fs::write(root.join("sentinel"), b"keep").unwrap();
    for (id, asset_name) in [
        ("tar-success", "tool.tar.gz"),
        ("zip-success", "tool.zip"),
        ("tar-success", "custom-release"),
        ("zip-success", "custom-release"),
        ("tar-traversal", "tool.tar.gz"),
        ("zip-traversal", "tool.zip"),
    ] {
        let case = fixture.cases.iter().find(|case| case.id == id).unwrap();
        let archive = std::fs::read(archive_root.join(&case.archive)).unwrap();
        let destination = root.join(format!("{id}-{}", asset_name.replace('.', "_")));
        std::fs::create_dir(&destination).unwrap();
        let result =
            extract_binary_to_dir(&archive, asset_name, &destination, &case.expected_binary);
        if let Some(error) = &case.error {
            assert_eq!(result.unwrap_err(), error.message, "{id}");
            assert!(!destination.join("escape").exists(), "{id}");
        } else {
            let path = result.unwrap();
            assert_eq!(
                path.strip_prefix(&destination).unwrap().to_string_lossy(),
                case.selected_binary
            );
            let selected = case
                .files
                .iter()
                .find(|file| file.path == case.selected_binary)
                .unwrap();
            assert_eq!(
                std::fs::read(path).unwrap(),
                selected.content.as_bytes(),
                "{id}"
            );
        }
    }
    assert_eq!(std::fs::read(root.join("sentinel")).unwrap(), b"keep");
    std::fs::remove_dir_all(root).unwrap();
}
