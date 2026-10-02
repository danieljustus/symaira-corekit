use std::path::PathBuf;

/// Resolve only the exact target-native oracle slice. Missing platform evidence is
/// an error, never a skip or a Darwin fixture relabeled for another target.
pub fn fixture_path(lane: &str) -> PathBuf {
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
        "../../testdata/rust-port/fixtures/update/static-v1/{goos}-{goarch}/{lane}.json"
    ));
    assert!(
        path.is_file(),
        "missing native Go update-oracle capture for {goos}/{goarch} lane {lane}: {}",
        path.display()
    );
    path
}
