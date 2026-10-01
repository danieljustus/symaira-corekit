use std::fs;
use std::path::PathBuf;
use symaira_core_update::extract::extract_binary_to_dir;

#[test]
fn extraction_cannot_follow_existing_links_outside_staging() {
    let root = std::env::temp_dir().join(format!("update-containment-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let outside = root.join("outside");
    fs::create_dir(&outside).unwrap();
    fs::write(outside.join("tool"), b"keep").unwrap();
    let fixtures = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../scripts/rust-port/update-extract-oracle/testdata");
    for (archive, asset) in [
        ("tar-success.tar.gz", "tool.tar.gz"),
        ("zip-success.zip", "tool.zip"),
    ] {
        let stage = root.join(asset);
        fs::create_dir(&stage).unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(&outside, stage.join("bundle")).unwrap();
        #[cfg(windows)]
        std::os::windows::fs::symlink_dir(&outside, stage.join("bundle")).unwrap();
        let result = extract_binary_to_dir(
            &fs::read(fixtures.join(archive)).unwrap(),
            asset,
            &stage,
            "tool",
        );
        assert!(result.is_err(), "external directory link accepted: {asset}");
        assert_eq!(fs::read(outside.join("tool")).unwrap(), b"keep");
        assert!(!outside.join("LICENSE").exists());
        fs::remove_file(stage.join("bundle"))
            .or_else(|_| fs::remove_dir(stage.join("bundle")))
            .unwrap();
    }
    fs::remove_dir_all(root).unwrap();
}
