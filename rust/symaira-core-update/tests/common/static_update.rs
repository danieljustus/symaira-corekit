use std::path::PathBuf;

/// Honor the caller's explicit candidate fixture for all replay tests. Otherwise
/// require the exact native slice, never a skip or another platform's capture.
pub fn fixture_path(lane: &str) -> PathBuf {
    let variable = match lane {
        "version" => "UPDATE_VERSION_FIXTURE",
        "response" => "RESPONSE_FIXTURE",
        "install-method" => "INSTALL_METHOD_FIXTURE",
        "extract" => "EXTRACT_FIXTURE",
        "swap" => "UPDATE_SWAP_FIXTURE",
        "checker" => "UPDATE_CHECKER_FIXTURE",
        other => panic!("unknown static update-oracle lane {other}"),
    };
    if let Some(path) = std::env::var_os(variable) {
        return PathBuf::from(path);
    }
    let goos = match std::env::consts::OS {
        "macos" => "darwin",
        "linux" => "linux",
        "windows" => "windows",
        other => panic!("no static update-oracle capture for target OS {other}"),
    };
    let goarch = match std::env::consts::ARCH {
        "aarch64" => "arm64",
        "x86_64" => "amd64",
        other => panic!("no static update-oracle capture for target architecture {other}"),
    };
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!(
        "../../testdata/rust-port/fixtures/update/static-v2/{goos}-{goarch}/{lane}.json"
    ));
    assert!(
        path.is_file(),
        "missing native Go update-oracle capture for {goos}/{goarch} lane {lane}: {}",
        path.display()
    );
    path
}
