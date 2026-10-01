use serde::Deserialize;
use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use symaira_core_update::install_method::InstallMethod;
use symaira_core_update::install_method::detect_with;

#[derive(Deserialize)]
struct Fixture {
    #[serde(default)]
    goos: Option<String>,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    path: String,
    #[serde(default)]
    env: HashMap<String, String>,
    method: String,
    error: String,
    self_update: bool,
    guidance: String,
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
fn install_method_observations_match_go_api() {
    let default_fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/rust-port/fixtures/update/install-methods.json");
    let fixture_path = std::env::var_os("INSTALL_METHOD_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_slice(&fs::read(fixture_path).unwrap()).unwrap();
    if let Some(reason) = platform_mismatch(fixture.goos.as_deref()) {
        eprintln!("SKIP {reason}");
        return;
    }
    assert_eq!(fixture.cases.len(), 15);

    let temp = std::env::temp_dir().join(format!("upd008-rust-{}", std::process::id()));
    let _ = fs::remove_dir_all(&temp);
    fs::create_dir_all(temp.join("home")).unwrap();
    fs::create_dir_all(temp.join("Cellar/tool/1.0.0/bin")).unwrap();
    fs::write(temp.join("Cellar/tool/1.0.0/bin/tool"), b"fixture").unwrap();
    fs::create_dir_all(temp.join("link")).unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink(
        temp.join("Cellar/tool/1.0.0/bin/tool"),
        temp.join("link/tool"),
    )
    .unwrap();
    #[cfg(windows)]
    std::os::windows::fs::symlink_file(
        temp.join("Cellar/tool/1.0.0/bin/tool"),
        temp.join("link/tool"),
    )
    .unwrap();
    fs::create_dir_all(temp.join("readonly")).unwrap();
    let mut readonly = fs::metadata(temp.join("readonly")).unwrap().permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        readonly.set_mode(0o555);
    }
    #[cfg(windows)]
    readonly.set_readonly(true);
    fs::set_permissions(temp.join("readonly"), readonly).unwrap();

    for case in fixture.cases {
        let path = case.path.replace("${TMP}", temp.to_str().unwrap());
        let environment: HashMap<String, String> = case
            .env
            .iter()
            .map(|(key, value)| (key.clone(), value.replace("${TMP}", temp.to_str().unwrap())))
            .collect();
        let home_key = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
        let home = environment
            .get(home_key)
            .map(PathBuf::from)
            .or_else(|| std::env::var_os(home_key).map(PathBuf::from));
        let result = detect_with(Path::new(&path), &environment, home.as_deref());
        assert_eq!(
            result.as_ref().err().copied().unwrap_or(""),
            case.error,
            "{}",
            case.id
        );
        let method = result.unwrap_or(InstallMethod::Unknown);
        assert_eq!(method.as_str(), case.method, "{}", case.id);
        assert_eq!(
            method.self_update_supported(),
            case.self_update,
            "{}",
            case.id
        );
        assert_eq!(method.guidance("symvault"), case.guidance, "{}", case.id);
    }
    let _ = fs::remove_dir_all(temp);
}
