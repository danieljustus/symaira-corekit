//! Opt-in end-to-end Apply against a pinned, public, keyless-signed release.
//! The only replaced executable is an isolated disposable test file.
use sha2::{Digest, Sha256};
use std::fs;
use std::path::{Path, PathBuf};
use symaira_core_update::applier::Applier;
use symaira_core_update::cosign::Config;
use symaira_core_update::{Asset, Release};

#[test]
#[ignore = "requires pinned public release assets, a real Cosign CLI and network"]
fn real_signed_release_only_replaces_disposable_target() {
    let fixture = PathBuf::from(std::env::var("COSIGN_VALID_FIXTURE_DIR").unwrap());
    let checksums = fs::read(fixture.join("symaira-vault_0.22.1_checksums.txt")).unwrap();
    let digest: String = Sha256::digest(&checksums)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    assert_eq!(
        digest,
        "e722249e12a560717f67af31db4d5153186442a243aee1a14b2a42a02f97ee05"
    );
    let goos = match std::env::consts::OS {
        "macos" => "darwin",
        other => other,
    };
    let goarch = match std::env::consts::ARCH {
        "aarch64" => "arm64",
        "x86_64" => "amd64",
        other => other,
    };
    let extension = if goos == "windows" { "zip" } else { "tar.gz" };
    let name = format!("symaira-vault_0.22.1_{goos}_{goarch}.{extension}");
    assert!(
        String::from_utf8_lossy(&checksums)
            .lines()
            .any(|line| line.ends_with(&name)),
        "the real asset needs an entry in the signed manifest"
    );
    let base = "https://github.com/danieljustus/symaira-vault/releases/download/v0.22.1";
    let release = Release {
        tag_name: "v0.22.1".into(),
        body: String::new(),
        html_url: String::new(),
        assets: vec![
            Asset {
                name: name.clone(),
                browser_download_url: format!("{base}/{name}"),
                size: 0,
            },
            Asset {
                name: "symaira-vault_0.22.1_checksums.txt".into(),
                browser_download_url: format!("{base}/symaira-vault_0.22.1_checksums.txt"),
                size: 0,
            },
        ],
    };
    let config = Config {
        repo: "danieljustus/symaira-vault",
        binary_name: "symaira-vault",
        download_base_url: None,
        identity_regexp: None,
    };
    let root = std::env::temp_dir().join(format!("corekit-signed-apply-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    let binary = if goos == "windows" {
        "symvault.exe"
    } else {
        "symvault"
    };
    let target = root.join(binary);
    fs::write(&target, b"old disposable binary").unwrap();
    let mut backup = target.as_os_str().to_os_string();
    backup.push(".bak");
    let backup = PathBuf::from(backup);
    let applier = Applier {
        goos,
        goarch,
        cosign: Some(&config),
        extract_binary: Some(binary),
        ..Applier::default()
    };
    let mut saw_backup = false;
    let mut validate = |installed: &Path| {
        saw_backup = backup.exists();
        let length = fs::metadata(installed)
            .map_err(|error| error.to_string())?
            .len();
        if length > 1024 {
            Ok(())
        } else {
            Err("installed binary is too small".into())
        }
    };
    applier
        .apply(&release, &target, None, Some(&mut validate))
        .unwrap();
    assert!(
        saw_backup,
        "validation must run while rollback is available"
    );
    assert!(fs::metadata(&target).unwrap().len() > 1024);
    assert!(!backup.exists());
    fs::remove_dir_all(root).unwrap();
}
