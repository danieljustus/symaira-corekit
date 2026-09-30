use std::{
    io::{Read, Write},
    net::TcpListener,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
    thread,
};
use symaira_core_update::{
    cache::{DEFAULT_CACHE_TTL, check},
    extract::extract_binary_to_dir,
};

static ID: AtomicU64 = AtomicU64::new(0);
#[cfg(target_os = "macos")]
#[test]
fn descheduled_caller_cannot_accept_a_ready_response_after_timeout() {
    use std::time::Duration;
    unsafe extern "C" {
        fn mach_thread_self() -> u32;
        fn thread_suspend(thread: u32) -> i32;
        fn thread_resume(thread: u32) -> i32;
        fn mach_port_deallocate(task: u32, name: u32) -> i32;
        static mach_task_self_: u32;
    }
    // Suspend only this test's caller, not Reqwest's runtime. A ready response
    // must still be rejected when the caller resumes beyond its 30 ms budget.
    let caller = unsafe { mach_thread_self() };
    for timeout in [Duration::from_millis(30), Duration::ZERO] {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}/", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = Vec::new();
            let mut byte = [0];
            while !request.ends_with(b"\r\n\r\n") {
                stream.read_exact(&mut byte).unwrap();
                request.push(byte[0]);
            }
            // The port names the live caller in this process and remains valid
            // until both synchronized server threads have joined.
            assert_eq!(unsafe { thread_suspend(caller) }, 0);
            let result = stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}");
            thread::sleep(Duration::from_millis(150));
            // Resume before any fallible assertion about the server write.
            assert_eq!(unsafe { thread_resume(caller) }, 0);
            result.unwrap();
        });
        let result = symaira_core_update::request::fetch(&url, "1.2.3", timeout);
        server.join().unwrap();
        if timeout.is_zero() {
            assert_eq!(result.unwrap().status, 200);
        } else {
            assert_eq!(result.unwrap_err().code, "timeout");
        }
    }
    assert_eq!(unsafe { mach_port_deallocate(mach_task_self_, caller) }, 0);
}

fn root() -> PathBuf {
    let path = std::env::temp_dir().join(format!(
        "update-integrity-{}-{}",
        std::process::id(),
        ID.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir(&path).unwrap();
    path
}

fn zip(deflated: bool) -> Vec<u8> {
    let body = b"verified tool\n";
    let compressed = if deflated {
        let mut encoder =
            flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::default());
        encoder.write_all(body).unwrap();
        encoder.finish().unwrap()
    } else {
        body.to_vec()
    };
    let mut crc = flate2::Crc::new();
    crc.update(body);
    let method = if deflated { 8u16 } else { 0 };
    let mut data = Vec::new();
    data.extend(0x04034b50u32.to_le_bytes());
    for field in [20u16, 0, method, 0, 0] {
        data.extend(field.to_le_bytes());
    }
    for field in [crc.sum(), compressed.len() as u32, body.len() as u32] {
        data.extend(field.to_le_bytes());
    }
    data.extend(4u16.to_le_bytes());
    data.extend(0u16.to_le_bytes());
    data.extend(b"tool");
    data.extend(compressed);
    let central = data.len() as u32;
    data.extend(0x02014b50u32.to_le_bytes());
    for field in [20u16, 20, 0, method, 0, 0] {
        data.extend(field.to_le_bytes());
    }
    for field in [crc.sum(), (central - 34), body.len() as u32] {
        data.extend(field.to_le_bytes());
    }
    for field in [4u16, 0, 0, 0, 0] {
        data.extend(field.to_le_bytes());
    }
    data.extend((0o100600u32 << 16).to_le_bytes());
    data.extend(0u32.to_le_bytes());
    data.extend(b"tool");
    let central_size = data.len() as u32 - central;
    data.extend(0x06054b50u32.to_le_bytes());
    for field in [0u16, 0, 1, 1] {
        data.extend(field.to_le_bytes());
    }
    data.extend(central_size.to_le_bytes());
    data.extend(central.to_le_bytes());
    data.extend(0u16.to_le_bytes());
    data
}

#[test]
fn stored_and_deflated_zip_integrity_is_required_before_selection() {
    for deflated in [false, true] {
        let valid = zip(deflated);
        let central = valid.windows(4).position(|v| v == b"PK\x01\x02").unwrap();
        for mutation in [None, Some(16usize), Some(24)] {
            let root = root();
            let mut data = valid.clone();
            if let Some(offset) = mutation {
                data[central + offset] ^= 1;
            }
            let result = extract_binary_to_dir(&data, "tool.zip", &root, "tool");
            if mutation.is_none() {
                assert_eq!(std::fs::read(result.unwrap()).unwrap(), b"verified tool\n");
            } else {
                assert!(result.unwrap_err().contains("zip: checksum error"));
                assert!(!root.join("tool").exists());
            }
            std::fs::remove_dir_all(root).unwrap();
        }
    }
}

fn fetch_body(body: &'static str, cache: &std::path::Path) -> symaira_core_update::cache::Outcome {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}/", listener.local_addr().unwrap());
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut byte = [0];
        while !request.ends_with(b"\r\n\r\n") {
            stream.read_exact(&mut byte).unwrap();
            request.push(byte[0]);
        }
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
            body.len()
        )
        .unwrap();
    });
    let outcome = check(&url, cache, DEFAULT_CACHE_TTL, true, 1000);
    server.join().unwrap();
    outcome
}

#[test]
fn apply_rejects_corrupt_zip_even_with_a_matching_outer_sha256() {
    use sha2::{Digest, Sha256};
    use symaira_core_update::{Asset, Release, applier::Applier};
    for deflated in [false, true] {
        for corrupt in [false, true] {
            let root = root();
            let target = root.join("tool");
            std::fs::write(&target, b"old tool").unwrap();
            let mut archive = zip(deflated);
            if corrupt {
                let central = archive.windows(4).position(|v| v == b"PK\x01\x02").unwrap();
                archive[central + 16] ^= 1;
            }
            let name = "tool_linux_amd64.zip";
            let digest: String = Sha256::digest(&archive)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
            let checksums = format!("{digest}  {name}\n");
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            let base = format!("http://{}", listener.local_addr().unwrap());
            let server = thread::spawn(move || {
                for body in [checksums.as_bytes(), archive.as_slice()] {
                    let (mut stream, _) = listener.accept().unwrap();
                    let mut request = Vec::new();
                    let mut byte = [0];
                    while !request.ends_with(b"\r\n\r\n") {
                        stream.read_exact(&mut byte).unwrap();
                        request.push(byte[0]);
                    }
                    write!(
                        stream,
                        "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                        body.len()
                    )
                    .unwrap();
                    stream.write_all(body).unwrap();
                }
            });
            let release = Release {
                tag_name: "v1.3.0".into(),
                body: String::new(),
                html_url: String::new(),
                assets: vec![
                    Asset {
                        name: name.into(),
                        browser_download_url: format!("{base}/archive"),
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
                extract_binary: Some("tool"),
                client: Some(
                    reqwest::blocking::Client::builder()
                        .timeout(std::time::Duration::from_secs(2))
                        .build()
                        .unwrap(),
                ),
                ..Applier::default()
            };
            let result = applier.apply(&release, &target, None, None);
            server.join().unwrap();
            if corrupt {
                assert!(result.unwrap_err().contains("zip: checksum error"));
                assert_eq!(std::fs::read(&target).unwrap(), b"old tool");
            } else {
                result.unwrap();
                assert_eq!(std::fs::read(&target).unwrap(), b"verified tool\n");
            }
            assert_eq!(std::fs::read_dir(&root).unwrap().count(), 1);
            std::fs::remove_dir_all(root).unwrap();
        }
    }
}

#[test]
fn full_json_decode_and_cache_replay() {
    for body in [
        r#"{"tag_name":"v1.3.0"}"#,
        "{\n  \"tag_name\" : \"v1.3.0\",\n  \"body\" : \"Grüße 😀\"\n}",
        r#"{"tag_name":"v1.\u0033.0","body":"\ud83d\ude00"}"#,
        r#"{"tag_name":" v1.3.0 ","html_url":" https://example.test/release ","assets":[{"name":"tool.zip","browser_download_url":"https://example.test/tool","size":42}]}"#,
    ] {
        let root = root();
        let cache = root.join("cache.json");
        let result = fetch_body(body, &cache);
        assert_eq!(result.release.unwrap().tag_name, "v1.3.0");
        let disk: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&cache).unwrap()).unwrap();
        assert_eq!(disk["release"]["TagName"], "v1.3.0");
        assert!(disk["release"].get("tag_name").is_none());
        if body.contains("ud83d") {
            assert_eq!(disk["release"]["Body"], "😀");
        }
        if body.contains("browser_download_url") {
            assert_eq!(disk["release"]["HTMLURL"], "https://example.test/release");
            assert_eq!(
                disk["release"]["Assets"][0]["BrowserDownloadURL"],
                "https://example.test/tool"
            );
            assert_eq!(disk["release"]["Assets"][0]["Size"], 42);
        }
        let replay = check(
            "http://127.0.0.1:0/",
            &cache,
            DEFAULT_CACHE_TTL,
            false,
            1001,
        );
        assert_eq!(replay.release.unwrap().tag_name, "v1.3.0");
        assert!(replay.error.is_none());
        std::fs::remove_dir_all(root).unwrap();
    }
    for body in [
        r#"{"tag_name":"v1.3.0" garbage}"#,
        r#"{"tag_name":13}"#,
        r#"{"tag_name":null}"#,
        r#"{"tag_name":"v1.3.0","body":false}"#,
        r#"{"tag_name":"v1.3.0","assets":[{"size":"13"}]}"#,
        r#"{"tag_name":"\ud800"}"#,
        r#"{"tag_name":"v1.3.0"} trailing"#,
    ] {
        let root = root();
        let cache = root.join("cache.json");
        assert!(fetch_body(body, &cache).error.is_some(), "accepted {body}");
        assert!(!cache.exists());
        std::fs::remove_dir_all(root).unwrap();
    }
}

#[test]
fn timestamp_and_cache_document_validation_never_panics() {
    let root = root();
    let cache = root.join("cache.json");
    for timestamp in [
        "1969-12-31T23:59:59Z",
        "0001-01-01T00:00:00Z",
        "2026-02-30T00:00:00Z",
        "2026-01-01T24:00:00Z",
        "2026-01-01T00:00:00",
        "2026-01-01T00:00:00.xZ",
        "2026-01-01T+1:00:00Z",
        "2026-01-01T00:00:00+-1:00",
    ] {
        std::fs::write(
            &cache,
            format!(r#"{{"timestamp":"{timestamp}","release":{{"TagName":"v1.3.0"}}}}"#),
        )
        .unwrap();
        let result = check("invalid URL", &cache, DEFAULT_CACHE_TTL, false, 1000);
        assert!(result.error.is_some(), "accepted timestamp {timestamp}");
    }
    for timestamp in [
        "1970-01-01T00:00:01Z",
        "1970-01-01T01:00:01+01:00",
        "9999-12-31T23:59:59.999Z",
    ] {
        std::fs::write(&cache, format!("{{\n \"timestamp\": \"{timestamp}\",\n \"release\": {{\"TagName\": \"v1.3.0\"}}\n}}")).unwrap();
        assert_eq!(
            check("invalid URL", &cache, DEFAULT_CACHE_TTL, false, 1000)
                .release
                .unwrap()
                .tag_name,
            "v1.3.0"
        );
    }
    for raw in [
        r#"{"timestamp":"1970-01-01T00:00:01Z","release":{"tag_name":"v1.3.0"}} garbage"#,
        r#"{"timestamp":1000,"release":{"tag_name":"v1.3.0"}}"#,
    ] {
        std::fs::write(&cache, raw).unwrap();
        assert!(
            check("invalid URL", &cache, DEFAULT_CACHE_TTL, false, 1000)
                .error
                .is_some()
        );
    }
    std::fs::remove_dir_all(root).unwrap();
}
