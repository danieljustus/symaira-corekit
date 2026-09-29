#![cfg(windows)]

use std::{fs, process::Command};
use symaira_core_update::install_method::{InstallMethod, detect, detect_with};

#[test]
fn existing_home_binaries_use_native_home_and_path_components() {
    if let Some(home) = std::env::var_os("COREKIT_INSTALL_HOME_CHILD") {
        let home = std::path::PathBuf::from(home);
        for (components, expected) in [
            (&["bin"][..], InstallMethod::DirectDownload),
            (&[".local", "bin"][..], InstallMethod::DirectDownload),
            (&[".cargo", "bin"][..], InstallMethod::DirectDownload),
            (&["go", "bin"][..], InstallMethod::GoInstall),
        ] {
            let binary = components
                .iter()
                .fold(home.clone(), |p, c| p.join(c))
                .join("tool.exe");
            assert_eq!(
                detect_with(&binary, &Default::default(), Some(&home)).unwrap(),
                expected
            );
            assert_eq!(detect(&binary).unwrap(), expected);
        }
        return;
    }
    let root = std::env::temp_dir().join(format!("native-home-{}", std::process::id()));
    fs::create_dir(&root).unwrap();
    for components in [
        ["bin", ""],
        [".local", "bin"],
        [".cargo", "bin"],
        ["go", "bin"],
    ] {
        let dir = components.iter().fold(root.clone(), |p, c| p.join(c));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("tool.exe"), b"fixture").unwrap();
    }
    let status = Command::new(std::env::current_exe().unwrap())
        .arg("--exact")
        .arg("existing_home_binaries_use_native_home_and_path_components")
        .env("COREKIT_INSTALL_HOME_CHILD", &root)
        .env("USERPROFILE", &root)
        .env_remove("HOME")
        .env_remove("GOPATH")
        .env_remove("GOMODCACHE")
        .env_remove("HOMEBREW_PREFIX")
        .status()
        .unwrap();
    fs::remove_dir_all(root).unwrap();
    assert!(status.success());
}

#[test]
fn mixed_separator_inputs_match_native_go_environment_rules() {
    let root = std::env::temp_dir().join(format!("native-install-mixed-{}", std::process::id()));
    assert!(!root.exists());
    for (directory, key, expected) in [
        ("brew", "HOMEBREW_PREFIX", InstallMethod::BuildFromSource),
        ("gopath", "GOPATH", InstallMethod::GoInstall),
        ("modcache", "GOMODCACHE", InstallMethod::BuildFromSource),
    ] {
        let prefix = format!("{}/{directory}", root.display());
        let binary = format!("{prefix}/bin/tool.exe");
        let environment = std::collections::HashMap::from([(key.to_owned(), prefix)]);
        assert_eq!(
            detect_with(std::path::Path::new(&binary), &environment, None).unwrap(),
            expected,
            "{key}"
        );
    }
}
