use std::{path::Path, time::Duration};
use symaira_core_update::{
    CancellationToken, Checker, applier::Applier, cosign, install_method, request,
};

fn recorded() -> serde_json::Value {
    let path = std::env::var("UPDATE_CANCELLATION_FIXTURE").unwrap_or_else(|_| {
        format!(
            "{}/../../testdata/rust-port/fixtures/update/cancellation.json",
            env!("CARGO_MANIFEST_DIR")
        )
    });
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}

#[tokio::test]
async fn pre_cancelled_public_apis_do_not_touch_paths_or_network() {
    let fixture = recorded();
    for op in ["checker", "signature", "certificate", "applier"] {
        let id = format!("{op}-pre");
        let expected = fixture
            .as_array()
            .unwrap()
            .iter()
            .find(|case| case["id"] == id)
            .unwrap();
        assert_eq!(
            expected["cancelled"], true,
            "pre-cancellation Go observation mismatch: {id}"
        );
        assert_eq!(expected["cache"], false);
        assert_eq!(expected["residue"], false);
    }
    let token = CancellationToken::new();
    token.cancel();
    let client = request::secure_async_download_client_builder(Duration::from_secs(1))
        .build()
        .unwrap();
    let mut checker = Checker::new("owner", "repo");
    checker.cache_path = Path::new("/nonexistent/update-cancelled-cache").into();
    assert_eq!(
        checker
            .check_with_force_cancellable("1.0.0", false, &client, &token)
            .await
            .unwrap_err(),
        "context canceled"
    );
    let config = cosign::Config {
        repo: "owner/repo",
        binary_name: "tool",
        download_base_url: None,
        identity_regexp: None,
    };
    assert_eq!(
        config
            .fetch_signature_cancellable("1.0.1", &client, &token)
            .await
            .unwrap_err(),
        "context canceled"
    );
    assert_eq!(
        config
            .fetch_certificate_cancellable("1.0.1", &client, &token)
            .await
            .unwrap_err(),
        "context canceled"
    );
    assert_eq!(
        config
            .verify_signature_cancellable(b"", b"", b"", &token)
            .await
            .unwrap_err(),
        "context canceled"
    );
    let release = symaira_core_update::Release {
        tag_name: "v1.0.1".into(),
        body: String::new(),
        html_url: String::new(),
        assets: vec![],
    };
    assert_eq!(
        Applier::default()
            .apply_cancellable(
                &release,
                Path::new("/nonexistent/tool"),
                None,
                None,
                &client,
                &token
            )
            .await
            .unwrap_err(),
        "context canceled"
    );
}

#[test]
fn empty_path_has_typed_error_identity_through_source_chain() {
    use std::error::Error;
    let error = install_method::detect_typed(Path::new("")).unwrap_err();
    let fixture = recorded();
    let expected = fixture
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["id"] == "empty-path")
        .unwrap();
    assert_eq!(expected["message"], error.to_string());
    assert_eq!(
        expected["identity"],
        error == install_method::ERR_EMPTY_BINARY_PATH
    );

    assert_eq!(error, install_method::ERR_EMPTY_BINARY_PATH);
    assert_eq!(
        error.to_string(),
        install_method::detect(Path::new("")).unwrap_err()
    );
    #[derive(Debug)]
    struct Wrapped(install_method::EmptyBinaryPath);
    impl std::fmt::Display for Wrapped {
        fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            write!(f, "wrapped: {}", self.0)
        }
    }
    impl Error for Wrapped {
        fn source(&self) -> Option<&(dyn Error + 'static)> {
            Some(&self.0)
        }
    }
    let wrapped = Wrapped(error);
    assert_eq!(
        wrapped
            .source()
            .unwrap()
            .downcast_ref::<install_method::EmptyBinaryPath>(),
        Some(&install_method::ERR_EMPTY_BINARY_PATH)
    );
}

#[tokio::test]
#[ignore = "requires the live Go oracle TLS server and freshly recorded fixture"]
async fn public_cancellation_replays_go() {
    use serde_json::json;
    use symaira_core_update::{Asset, Release};
    let fixture: serde_json::Value = serde_json::from_slice(
        &std::fs::read(std::env::var("UPDATE_CANCELLATION_FIXTURE").unwrap()).unwrap(),
    )
    .unwrap();
    let url = std::env::var("UPDATE_CANCELLATION_URL").unwrap();
    let root = std::env::temp_dir().join(format!("rust-update-cancel-{}", std::process::id()));
    std::fs::create_dir(&root).unwrap();
    let ready = root.join("ready");
    let cert = reqwest::tls::Certificate::from_der(
        &std::fs::read(std::env::var("UPDATE_CANCELLATION_CERT").unwrap()).unwrap(),
    )
    .unwrap();
    let mut headers = reqwest::header::HeaderMap::new();
    headers.insert("X-Ready", ready.to_str().unwrap().parse().unwrap());
    let metadata_client = request::secure_async_client_builder(Duration::from_secs(5))
        .tls_certs_only([cert.clone()])
        .default_headers(headers.clone())
        .build()
        .unwrap();
    let client = request::secure_async_download_client_builder(Duration::from_secs(5))
        .tls_certs_only([cert])
        .default_headers(headers)
        .build()
        .unwrap();
    let mut observations = vec![];
    for op in ["checker", "signature", "certificate", "applier"] {
        for phase in ["pre", "metadata", "body", "asset-body"] {
            if phase == "asset-body" && op != "applier" {
                continue;
            }
            let token = CancellationToken::new();
            if phase == "pre" {
                token.cancel();
            }
            let cache = root.join(format!("{op}-{phase}.json"));
            let target = root.join(format!("{op}-{phase}-tool"));
            std::fs::write(&target, "old").unwrap();
            let base = format!("{url}/{phase}");
            let mut checker = Checker::new("owner", "repo");
            checker.latest_release_url = base.clone();
            checker.cache_path = cache.clone();
            let config = cosign::Config {
                repo: "owner/repo",
                binary_name: "tool",
                download_base_url: Some(&base),
                identity_regexp: None,
            };
            let release = Release {
                tag_name: "v1.0.1".into(),
                body: String::new(),
                html_url: String::new(),
                assets: vec![
                    Asset {
                        name: "tool_linux_amd64".into(),
                        browser_download_url: format!("{base}/asset"),
                        size: 0,
                    },
                    Asset {
                        name: "checksums.txt".into(),
                        browser_download_url: format!("{base}/checksums"),
                        size: 0,
                    },
                ],
            };
            let applier = Applier {
                goos: "linux",
                goarch: "amd64",
                ..Applier::default()
            };
            let operation = async {
                let result = match op {
                    "checker" => checker
                        .check_with_force_cancellable("1.0.0", false, &metadata_client, &token)
                        .await
                        .map(|_| ()),
                    "signature" => config
                        .fetch_signature_cancellable("1.0.1", &client, &token)
                        .await
                        .map(|_| ()),
                    "certificate" => config
                        .fetch_certificate_cancellable("1.0.1", &client, &token)
                        .await
                        .map(|_| ()),
                    "applier" => {
                        applier
                            .apply_cancellable(&release, &target, None, None, &client, &token)
                            .await
                    }
                    _ => unreachable!(),
                };
                if let Err(error) = &result {
                    eprintln!("{op}/{phase}: {error}");
                }
                result
            };
            let cancellation = async {
                if phase == "pre" {
                    return;
                }
                tokio::time::timeout(Duration::from_secs(3), async {
                    while !ready.exists() {
                        tokio::time::sleep(Duration::from_millis(5)).await;
                    }
                })
                .await
                .expect("server readiness, not elapsed sleep, gates cancellation");
                token.cancel();
            };
            let (result, ()) = tokio::join!(operation, cancellation);
            observations.push(json!({"id":format!("{op}-{phase}"),"cancelled":result.unwrap_err().contains("context canceled"),"cache":cache.exists(),"target":std::fs::read_to_string(&target).unwrap(),"message":"","identity":false,"body":"","residue":std::fs::read_dir(&root).unwrap().any(|entry| entry.unwrap().file_name().to_string_lossy().starts_with("updateapply"))}));
            if ready.exists() {
                std::fs::remove_file(&ready).unwrap();
            }
        }
    }
    let error = install_method::detect_typed(Path::new("")).unwrap_err();
    observations.push(json!({"id":"empty-path","cancelled":false,"cache":false,"target":"","message":error.to_string(),"identity":error==install_method::ERR_EMPTY_BINARY_PATH,"body":"","residue":false}));
    let base = format!("{url}/injected");
    let config = cosign::Config {
        repo: "owner/repo",
        binary_name: "tool",
        download_base_url: Some(&base),
        identity_regexp: None,
    };
    let body = config
        .fetch_signature_cancellable("1.0.1", &client, &CancellationToken::new())
        .await
        .unwrap();
    observations.push(json!({"id":"injected-client","cancelled":false,"cache":false,"target":"","message":"","identity":false,"body":String::from_utf8(body).unwrap(),"residue":false}));
    observations.push(json!({"id":"issuer","cancelled":false,"cache":false,"target":"","message":"","identity":false,"body":cosign::OIDC_ISSUER,"residue":false}));
    assert_eq!(
        serde_json::Value::Array(observations),
        fixture,
        "public cancellation observation mismatch"
    );
    // Rust adds cancellation after mutation; Go has no context check here.
    let target = root.join("rollback-tool");
    std::fs::write(&target, "old").unwrap();
    let release = Release {
        tag_name: "v1.0.1".into(),
        body: String::new(),
        html_url: String::new(),
        assets: vec![
            Asset {
                name: "tool_linux_amd64".into(),
                browser_download_url: format!("{url}/apply/asset"),
                size: 3,
            },
            Asset {
                name: "checksums.txt".into(),
                browser_download_url: format!("{url}/apply/checksums"),
                size: 0,
            },
        ],
    };
    let token = CancellationToken::new();
    let mut validate = |path: &Path| {
        assert_eq!(std::fs::read_to_string(path).unwrap(), "new");
        token.cancel();
        Ok(())
    };
    let applier = Applier {
        goos: "linux",
        goarch: "amd64",
        ..Applier::default()
    };
    let error = applier
        .apply_cancellable(
            &release,
            &target,
            None,
            Some(&mut validate),
            &client,
            &token,
        )
        .await
        .unwrap_err();
    assert!(error.contains("context canceled"));
    assert_eq!(std::fs::read_to_string(&target).unwrap(), "old");
    assert!(!target.with_file_name("rollback-tool.bak").exists());
    std::fs::remove_dir_all(root).unwrap();
}

#[tokio::test]
#[ignore = "requires disposable Go helper installed as Cosign by the differential harness"]
async fn cancellable_verifier_reaps_native_owned_process_tree() {
    use std::process::{Command, Stdio};
    let ready = std::path::PathBuf::from(std::env::var_os("UPDATE_CANCEL_VERIFIER_READY").unwrap());
    let config = cosign::Config {
        repo: "owner/repo",
        binary_name: "tool",
        download_base_url: None,
        identity_regexp: None,
    };
    let token = CancellationToken::new();
    let verification =
        config.verify_signature_cancellable(b"content", b"signature", b"certificate", &token);
    let cancellation = async {
        tokio::time::timeout(Duration::from_secs(3), async {
            while !ready.is_file() {
                tokio::time::sleep(Duration::from_millis(5)).await;
            }
        })
        .await
        .expect("owned native descendant must signal readiness");
        token.cancel();
    };
    let (result, ()) = tokio::time::timeout(Duration::from_secs(5), async {
        tokio::join!(verification, cancellation)
    })
    .await
    .expect("native verifier cancellation must be bounded");
    assert_eq!(result.unwrap_err(), "context canceled");
    let pid = std::fs::read_to_string(ready).unwrap();
    let pid = pid.trim();
    assert!(pid.bytes().all(|b| b.is_ascii_digit()));
    tokio::time::timeout(Duration::from_secs(3), async {
        loop {
            #[cfg(unix)]
            let alive = Command::new("/bin/kill")
                .args(["-0", pid])
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .status()
                .unwrap()
                .success();
            #[cfg(windows)]
            let alive = {
                let output = Command::new("tasklist")
                    .args(["/FI", &format!("PID eq {pid}"), "/FO", "CSV", "/NH"])
                    .stderr(Stdio::null())
                    .output()
                    .unwrap();
                assert!(output.status.success());
                String::from_utf8_lossy(&output.stdout).lines().any(|line| {
                    line.split(',')
                        .nth(1)
                        .is_some_and(|field| field.trim_matches('"') == pid)
                })
            };
            if !alive {
                break;
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    })
    .await
    .expect("native owned descendant survived cancellation");
}
