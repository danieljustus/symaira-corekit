use std::path::PathBuf;

/// Select only the exact native Go capture for the Rust test target.
/// Missing platform slices are errors; another OS/architecture is never reused.
pub fn fixture_path(lane: &str) -> PathBuf {
    let goos = match std::env::consts::OS {
        "macos" => "darwin",
        "linux" => "linux",
        "windows" => "windows",
        other => panic!("unsupported update oracle target OS: {other}"),
    };
    let goarch = match std::env::consts::ARCH {
        "aarch64" => "arm64",
        "x86_64" => "amd64",
        other => panic!("unsupported update oracle target architecture: {other}"),
    };
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let path = root
        .join("testdata/rust-port/fixtures/update/static-v1")
        .join(format!("{goos}-{goarch}"))
        .join(format!("{lane}.json"));
    assert!(
        path.is_file(),
        "missing native Go update-oracle capture for {goos}/{goarch} lane {lane}: {}",
        path.display()
    );
    path
}
