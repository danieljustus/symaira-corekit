use serde::Deserialize;
use std::path::PathBuf;
use symaira_core_update::extract::observe;

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
    files: Vec<ExpectedFile>,
    error: Option<ExpectedError>,
}

#[derive(Deserialize)]
struct ExpectedFile {
    path: String,
    content: String,
    mode: u32,
}

#[derive(Debug, Deserialize, PartialEq, Eq)]
struct ExpectedError {
    code: String,
    message: String,
}

#[test]
fn extraction_matches_go_archives_and_filesystem_observations() {
    let fixture: Fixture = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/update/extract.json"
    ))
    .expect("valid generated extraction fixture");
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
