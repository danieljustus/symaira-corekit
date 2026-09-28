use serde::Deserialize;
use std::path::PathBuf;
use symaira_core_update::extract::observe;

#[derive(Deserialize)]
struct Fixture {
    #[serde(default)]
    goos: Option<String>,
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

/// The committed fixture records one platform's Go observations. On another
/// platform the fresh Go oracle plus the Rust replay in `make rust-update-contract`
/// assert parity instead of replaying foreign expectations.
fn platform_mismatch(recorded: Option<&str>) -> Option<String> {
    let current = if cfg!(target_os = "windows") {
        "windows"
    } else if cfg!(target_os = "macos") {
        "darwin"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else {
        ""
    };
    match recorded {
        Some(recorded) if recorded != current => Some(format!(
            "fixture recorded on {recorded}, running on {current}; cross-platform parity is asserted by make rust-update-contract"
        )),
        _ => None,
    }
}

#[test]
fn extraction_matches_go_archives_and_filesystem_observations() {
    let default_fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/rust-port/fixtures/update/extract.json");
    let fixture_path = std::env::var_os("EXTRACT_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_str(
        &std::fs::read_to_string(&fixture_path).expect("read generated extraction fixture"),
    )
    .expect("valid generated extraction fixture");
    if let Some(reason) = platform_mismatch(fixture.goos.as_deref()) {
        eprintln!("SKIP {reason}");
        return;
    }
    assert_eq!(fixture.cases.len(), 12);
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    for expected in fixture.cases {
        let archive = std::fs::read(root.join(&expected.archive))
            .unwrap_or_else(|err| panic!("{} archive: {err}", expected.id));
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
