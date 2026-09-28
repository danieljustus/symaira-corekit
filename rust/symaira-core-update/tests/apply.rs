use std::path::PathBuf;
use symaira_core_update::apply::{FileObservation, Input, Observation, replay};

#[derive(serde::Deserialize)]
struct Fixture {
    #[serde(default)]
    goos: Option<String>,
    cases: Vec<ExpectedCase>,
}

#[derive(serde::Deserialize)]
struct ExpectedCase {
    input: ExpectedInput,
    observation: ExpectedObservation,
}

#[derive(serde::Deserialize)]
struct ExpectedInput {
    id: String,
    asset_name: String,
    payload_hex: String,
    checksum_ok: bool,
    initial_exists: bool,
    initial_content: String,
    initial_mode: u32,
    #[serde(default)]
    extract_binary: String,
    #[serde(default)]
    validate_error: String,
    #[serde(default)]
    use_zip: bool,
    #[serde(default)]
    omit_asset: bool,
    #[serde(default)]
    blocked_parent: bool,
    #[serde(default)]
    nested_parent: bool,
}

#[derive(serde::Deserialize)]
struct ExpectedObservation {
    #[serde(default)]
    error_code: String,
    target_exists: bool,
    #[serde(default)]
    target_content: String,
    #[serde(default)]
    target_mode: u32,
    backup_exists: bool,
    stage_during_download: bool,
    temp_during_download: bool,
    validator_saw_target: bool,
    validator_saw_backup: bool,
    #[serde(default)]
    validator_target_content: String,
    files: Vec<ExpectedFile>,
}

#[derive(serde::Deserialize)]
struct ExpectedFile {
    path: String,
    content: String,
    mode: u32,
}

impl ExpectedCase {
    fn input(&self) -> Input {
        Input {
            id: self.input.id.clone(),
            asset_name: self.input.asset_name.clone(),
            payload_hex: self.input.payload_hex.clone(),
            checksum_ok: self.input.checksum_ok,
            initial_exists: self.input.initial_exists,
            initial_content: self.input.initial_content.clone(),
            initial_mode: self.input.initial_mode,
            extract_binary: self.input.extract_binary.clone(),
            validate_error: self.input.validate_error.clone(),
            use_zip: self.input.use_zip,
            omit_asset: self.input.omit_asset,
            blocked_parent: self.input.blocked_parent,
            nested_parent: self.input.nested_parent,
        }
    }

    fn observation(&self) -> Observation {
        Observation {
            error_code: self.observation.error_code.clone(),
            target_exists: self.observation.target_exists,
            target_content: self.observation.target_content.clone(),
            target_mode: self.observation.target_mode,
            backup_exists: self.observation.backup_exists,
            stage_during_download: self.observation.stage_during_download,
            temp_during_download: self.observation.temp_during_download,
            validator_saw_target: self.observation.validator_saw_target,
            validator_saw_backup: self.observation.validator_saw_backup,
            validator_target_content: self.observation.validator_target_content.clone(),
            files: self
                .observation
                .files
                .iter()
                .map(|file| FileObservation {
                    path: file.path.clone(),
                    content: file.content.clone(),
                    mode: file.mode,
                })
                .collect(),
        }
    }
}

/// The committed fixture records one platform's Go observations. On another
/// platform `make rust-update-contract` replays this platform's fresh Go
/// observations through the same test instead of foreign expectations.
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
fn apply_filesystem_observations_match_go_fixture() {
    let default_fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/rust-port/fixtures/update/apply.json");
    let fixture_path = std::env::var_os("UPDATE_APPLY_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_slice(
        &std::fs::read(&fixture_path).expect("read generated apply fixture"),
    )
    .expect("valid generated apply fixture");
    if let Some(reason) = platform_mismatch(fixture.goos.as_deref()) {
        eprintln!("SKIP {reason}");
        return;
    }
    assert_eq!(fixture.cases.len(), 10);
    for case in fixture.cases {
        let input = case.input();
        let actual = replay(&input);
        assert_eq!(actual, case.observation(), "{} observation", input.id);
    }
}
