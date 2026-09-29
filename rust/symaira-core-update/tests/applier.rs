use reqwest::blocking::Client;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{BufRead, BufReader, Write};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};
use symaira_core_update::applier::Applier;
use symaira_core_update::{Asset, Release};

fn bytes_from_hex(raw: &str) -> Vec<u8> {
    raw.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap())
        .collect()
}

fn sha256_hex(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

/// A fresh Go oracle writes UPDATE_APPLY_FIXTURE in the differential. A
/// platform's committed fixture is used only by the native standalone test.
#[test]
fn production_applier_matches_go_filesystem_observations() {
    let fallback = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/rust-port/fixtures/update/apply.json");
    let fixture = std::env::var_os("UPDATE_APPLY_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(fallback);
    let data: Value = serde_json::from_slice(&fs::read(fixture).unwrap()).unwrap();
    let current = match std::env::consts::OS {
        "macos" => "darwin",
        other => other,
    };
    if data["goos"].as_str().unwrap() != current {
        eprintln!("SKIP production Applier: fixture has a different Go OS");
        return;
    }
    let test_root = std::env::temp_dir().join(format!(
        "symaira-production-apply-contract-{}",
        std::process::id()
    ));
    fs::create_dir(&test_root).unwrap();
    let cases = data["cases"].as_array().unwrap();
    assert_eq!(cases.len(), 17, "all Go Apply cases need production replay");
    for case in cases {
        let input = &case["input"];
        let id = input["id"].as_str().unwrap();
        let expected = &case["observation"];
        let parent = test_root.join(id);
        fs::create_dir(&parent).unwrap();
        let target_parent = if input["blocked_parent"].as_bool().unwrap_or(false) {
            let blocked = parent.join("blocked-parent");
            fs::write(&blocked, "blocker").unwrap();
            blocked
        } else if input["nested_parent"].as_bool().unwrap_or(false) {
            let nested = parent.join("nested");
            fs::create_dir(&nested).unwrap();
            nested
        } else {
            parent.clone()
        };
        let target = target_parent.join("mytool");
        if input["initial_exists"].as_bool().unwrap() {
            fs::write(&target, input["initial_content"].as_str().unwrap()).unwrap();
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(
                    &target,
                    fs::Permissions::from_mode(input["initial_mode"].as_u64().unwrap() as u32),
                )
                .unwrap();
            }
        }
        let payload = bytes_from_hex(input["payload_hex"].as_str().unwrap());
        let payload_len = payload.len() as u64;
        let name = input["asset_name"].as_str().unwrap();
        let checked = if input["checksum_ok"].as_bool().unwrap() {
            payload.as_slice()
        } else {
            b"different payload".as_slice()
        };
        let manifest = input["checksums_text"]
            .as_str()
            .map(str::as_bytes)
            .map_or_else(
                || format!("{}  {name}\n", sha256_hex(checked)).into_bytes(),
                Vec::from,
            );
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let requests = if input["omit_asset"].as_bool().unwrap_or(false)
            || name.to_ascii_lowercase().contains("checksums")
        {
            0
        } else if input["blocked_parent"].as_bool().unwrap_or(false)
            || input["checksums_text"]
                .as_str()
                .is_some_and(|text| text.split_whitespace().count() < 2 || !text.contains(name))
        {
            1
        } else {
            2
        };
        let stage_seen = Arc::new(AtomicBool::new(false));
        let observed_stage = Arc::clone(&stage_seen);
        let staging_parent = target_parent.clone();
        let server = std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(10);
            let mut handled = 0;
            while handled < requests && Instant::now() < deadline {
                let (mut stream, _) = match listener.accept() {
                    Ok(accepted) => accepted,
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(2));
                        continue;
                    }
                    Err(error) => panic!("fixture HTTP accept: {error}"),
                };
                let mut reader = BufReader::new(&stream);
                let mut request = String::new();
                reader.read_line(&mut request).unwrap();
                loop {
                    let mut header = String::new();
                    if reader.read_line(&mut header).unwrap() == 0 || header == "\r\n" {
                        break;
                    }
                }
                let body = if request.starts_with("GET /checksums ") {
                    &manifest
                } else if request.starts_with("GET /asset ") {
                    observed_stage.store(
                        fs::read_dir(&staging_parent).unwrap().any(|entry| {
                            entry
                                .unwrap()
                                .file_name()
                                .to_string_lossy()
                                .starts_with("updateapply-")
                        }),
                        Ordering::Relaxed,
                    );
                    &payload
                } else {
                    panic!("unexpected fixture request: {request}")
                };
                write!(
                    stream,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                )
                .unwrap();
                stream.write_all(body).unwrap();
                handled += 1;
            }
            assert_eq!(handled, requests, "fixture request count");
        });
        let release = Release {
            tag_name: "v1.2.3".into(),
            body: String::new(),
            html_url: String::new(),
            assets: vec![
                Asset {
                    name: name.into(),
                    browser_download_url: format!("{url}/asset"),
                    size: 0,
                },
                Asset {
                    name: "checksums.txt".into(),
                    browser_download_url: format!("{url}/checksums"),
                    size: 0,
                },
            ],
        };
        let client = Client::builder().no_proxy().build().unwrap();
        let applier = Applier {
            goos: if input["use_zip"].as_bool().unwrap_or(false) {
                "windows"
            } else {
                "linux"
            },
            goarch: "amd64",
            extract_binary: input["extract_binary"].as_str(),
            client: Some(client),
            ..Applier::default()
        };
        let validator_saw_target = Arc::new(AtomicBool::new(false));
        let validator_saw_backup = Arc::new(AtomicBool::new(false));
        let validate_error = input["validate_error"].as_str().unwrap_or("");
        let mut validator = |path: &Path| {
            validator_saw_target.store(path == target && path.exists(), Ordering::Relaxed);
            validator_saw_backup.store(
                target.with_file_name("mytool.bak").exists(),
                Ordering::Relaxed,
            );
            Err(validate_error.to_owned())
        };
        let mut progress = Vec::new();
        let outcome = applier.apply(
            &release,
            &target,
            Some(&mut |written, total| progress.push((written, total))),
            if validate_error.is_empty() {
                None
            } else {
                Some(&mut validator)
            },
        );
        server.join().unwrap();
        let error = expected["error_code"].as_str().unwrap_or("");
        match error {
            "" => assert!(outcome.is_ok(), "{id}: {outcome:?}"),
            "checksum_mismatch" => {
                assert!(outcome.unwrap_err().contains("checksum mismatch"), "{id}")
            }
            "validation_failed" => assert!(
                outcome.unwrap_err().contains("validate installed binary"),
                "{id}"
            ),
            "path_traversal" => assert!(outcome.unwrap_err().contains("path traversal"), "{id}"),
            "missing_asset" => assert!(
                outcome.unwrap_err().contains("no release asset matches"),
                "{id}"
            ),
            "apply_failed" => assert!(outcome.is_err(), "{id}"),
            other => panic!("unhandled Go result {id}: {other}"),
        }
        assert_eq!(
            target.exists(),
            expected["target_exists"].as_bool().unwrap(),
            "{id} target existence"
        );
        if target.exists() {
            assert_eq!(
                fs::read_to_string(&target).unwrap(),
                expected["target_content"].as_str().unwrap(),
                "{id} target content"
            );
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                assert_eq!(
                    fs::metadata(&target).unwrap().permissions().mode() & 0o777,
                    expected["target_mode"].as_u64().unwrap() as u32,
                    "{id} target mode"
                );
            }
        }
        assert_eq!(
            target.with_file_name("mytool.bak").exists(),
            expected["backup_exists"].as_bool().unwrap(),
            "{id} backup"
        );
        assert_eq!(
            stage_seen.load(Ordering::Relaxed),
            expected["stage_during_download"].as_bool().unwrap(),
            "{id} staged during download"
        );
        assert_eq!(
            validator_saw_target.load(Ordering::Relaxed),
            expected["validator_saw_target"].as_bool().unwrap(),
            "{id} validator target"
        );
        assert_eq!(
            validator_saw_backup.load(Ordering::Relaxed),
            expected["validator_saw_backup"].as_bool().unwrap(),
            "{id} validator backup"
        );
        if target_parent.is_dir() {
            assert!(
                !fs::read_dir(&target_parent).unwrap().any(|entry| entry
                    .unwrap()
                    .file_name()
                    .to_string_lossy()
                    .starts_with("updateapply-")),
                "{id} orphan staging path"
            );
        }
        if requests == 2 && payload_len > 0 {
            assert_eq!(
                progress.last().copied(),
                Some((payload_len, payload_len)),
                "{id} progress"
            );
        }
    }
    fs::remove_dir_all(test_root).unwrap();
}
