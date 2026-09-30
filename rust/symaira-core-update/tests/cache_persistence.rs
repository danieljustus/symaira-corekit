use serde::Deserialize;
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    path::PathBuf,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use symaira_core_update::cache::{DEFAULT_CACHE_TTL, check};

const NORMAL_BODY: &str = r#"{"tag_name":"v1.3.0","body":"HTML <>& \u2028 \u2029 literal\\u2028","html_url":" https://github.com/o/r/releases/tag/v1.3.0 ","assets":[{"name":"tool.tar.gz","browser_download_url":"https://github.com/o/r/releases/download/v1.3.0/tool.tar.gz","size":42}]}"#;
const DUPLICATE_TAG_BODY: &str = r#"{"TAG_NAME":"v1.2.0","tag_name":"v1.3.0"}"#;
const REPLACEMENT_BODY: &str = r#"{"tag_name":"v1.4.0","body":"replacement","assets":[]}"#;

#[derive(Debug, Deserialize)]
struct Fixture {
    cases: Vec<Case>,
    timestamp_samples: Vec<TimestampSample>,
    unix_mode_supported: bool,
}

#[derive(Debug, Deserialize)]
struct TimestampSample {
    unix_millis: u64,
    rfc3339_nano: String,
}

#[derive(Debug, Deserialize)]
struct Case {
    id: String,
    requests: usize,
    result: ResultValue,
    cache_bytes: Option<String>,
    cache_exists: bool,
    cache_mode: Option<u32>,
    directory_mode: Option<u32>,
    atomic_replace: Option<bool>,
    hardlink_preserved: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct ResultValue {
    tag: Option<String>,
    error: bool,
}

struct TempRoot(PathBuf);

impl TempRoot {
    fn new() -> Self {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or(Duration::ZERO)
            .as_nanos();
        let root = std::env::temp_dir().join(format!(
            "upd003-live-cache-rust-{}-{nonce}",
            std::process::id()
        ));
        fs::create_dir_all(&root).unwrap();
        Self(root)
    }
}

impl Drop for TempRoot {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn live_cache_persistence_matches_public_go_checker() {
    let Ok(path) = std::env::var("COREKIT_UPDATE_CACHE_LIVE") else {
        eprintln!("skipping live persistence differential: Go observation path is unset");
        return;
    };
    let fixture: Fixture = serde_json::from_slice(&fs::read(path).unwrap()).unwrap();
    let wanted = [
        "normal",
        "duplicate-tag-casefold",
        "trailing-json",
        "atomic-replace",
    ];
    assert_eq!(
        fixture
            .cases
            .iter()
            .map(|case| case.id.as_str())
            .collect::<Vec<_>>(),
        wanted
    );

    assert_eq!(fixture.unix_mode_supported, cfg!(unix));

    for expected in &fixture.cases {
        let actual = match expected.id.as_str() {
            "normal" => run_one(NORMAL_BODY, 1_000),
            "duplicate-tag-casefold" => run_one(DUPLICATE_TAG_BODY, 1_000),
            "trailing-json" => run_one(&format!("{NORMAL_BODY} trailing-data"), 1_000),
            "atomic-replace" => run_atomic_replace(),
            other => panic!("unexpected Go persistence case {other:?}"),
        };
        assert_eq!(
            actual.requests, expected.requests,
            "{}: request count",
            expected.id
        );
        assert_eq!(
            actual.tag.as_deref(),
            expected.result.tag.as_deref(),
            "{}: release tag",
            expected.id
        );
        assert_eq!(
            actual.error, expected.result.error,
            "{}: error presence",
            expected.id
        );
        assert_eq!(
            actual.cache_exists, expected.cache_exists,
            "{}: cache existence",
            expected.id
        );
        if let Some(expected_bytes) = &expected.cache_bytes {
            assert_eq!(
                actual.cache_bytes.as_deref(),
                Some(expected_bytes.as_str()),
                "{}: timestamp-normalized cache bytes",
                expected.id
            );
        }
        if fixture.unix_mode_supported && expected.cache_exists {
            assert_eq!(
                actual.cache_mode, expected.cache_mode,
                "{}: cache mode under umask 022",
                expected.id
            );
            assert_eq!(
                actual.directory_mode, expected.directory_mode,
                "{}: cache directory mode under umask 022",
                expected.id
            );
        }
        if let Some(expected) = expected.atomic_replace {
            assert_eq!(
                actual.atomic_replace,
                Some(expected),
                "atomic-replace: inode changed"
            );
        }
        if let Some(expected) = expected.hardlink_preserved {
            assert_eq!(
                actual.hardlink_preserved,
                Some(expected),
                "atomic-replace: old hardlink content preserved"
            );
        }
    }

    for sample in &fixture.timestamp_samples {
        let actual = run_one(NORMAL_BODY, u128::from(sample.unix_millis));
        assert_eq!(
            actual.timestamp.as_deref(),
            Some(sample.rfc3339_nano.as_str()),
            "timestamp format for {} Unix milliseconds",
            sample.unix_millis
        );
    }
}

#[test]
fn parent_dot_components_are_cleaned_before_directory_creation() {
    let root = TempRoot::new();
    let (url, server) = serve(vec![(200, NORMAL_BODY.to_owned())]);
    let cache_path = root
        .0
        .join("unused")
        .join("..")
        .join("cache")
        .join("cache.json");
    let result = check(&url, &cache_path, DEFAULT_CACHE_TTL, true, 1_000);
    server.join().unwrap();
    assert!(result.error.is_none());
    assert!(root.0.join("cache/cache.json").exists());
    assert!(!root.0.join("unused").exists());
}

#[test]
fn failed_cache_replacement_preserves_target_and_cleans_staging_file() {
    let root = TempRoot::new();
    let target = root.0.join("cache.json");
    fs::create_dir(&target).unwrap();
    fs::write(target.join("keep"), b"previous content").unwrap();
    let (url, server) = serve(vec![(200, NORMAL_BODY.to_owned())]);
    let result = check(&url, &target, DEFAULT_CACHE_TTL, true, 1_000);
    server.join().unwrap();
    // Like Go, an optional cache persistence failure does not fail the request.
    assert!(result.error.is_none());
    assert_eq!(fs::read(target.join("keep")).unwrap(), b"previous content");
    assert_eq!(fs::read_dir(&root.0).unwrap().count(), 1);
}

struct Actual {
    requests: usize,
    tag: Option<String>,
    error: bool,
    cache_exists: bool,
    cache_bytes: Option<String>,
    timestamp: Option<String>,
    cache_mode: Option<u32>,
    directory_mode: Option<u32>,
    atomic_replace: Option<bool>,
    hardlink_preserved: Option<bool>,
}

fn run_one(body: &str, now_ms: u128) -> Actual {
    let root = TempRoot::new();
    let (url, server) = serve(vec![(200, body.to_owned())]);
    let cache_path = root.0.join("cache").join("cache.json");
    let outcome = check(&url, &cache_path, DEFAULT_CACHE_TTL, false, now_ms);
    server.join().unwrap();
    let mut actual = Actual {
        requests: 1,
        tag: outcome.release.map(|release| release.tag_name),
        error: outcome.error.is_some(),
        cache_exists: cache_path.exists(),
        cache_bytes: None,
        timestamp: None,
        cache_mode: None,
        directory_mode: None,
        atomic_replace: None,
        hardlink_preserved: None,
    };
    if actual.cache_exists {
        let bytes = fs::read(&cache_path).unwrap();
        actual.timestamp = Some(cache_timestamp(&bytes));
        actual.cache_bytes = Some(normalize_timestamp(&bytes));
        set_modes(&mut actual, &cache_path);
    }
    actual
}

fn run_atomic_replace() -> Actual {
    let root = TempRoot::new();
    let (url, server) = serve(vec![
        (200, NORMAL_BODY.to_owned()),
        (200, REPLACEMENT_BODY.to_owned()),
    ]);
    let cache_path = root.0.join("cache").join("cache.json");
    let initial = check(&url, &cache_path, DEFAULT_CACHE_TTL, true, 1_000);
    assert!(initial.error.is_none(), "initial fetch failed: {initial:?}");
    let initial_file = fs::metadata(&cache_path).unwrap();
    let initial_bytes = fs::read(&cache_path).unwrap();
    let snapshot = cache_path.with_extension("snapshot");
    fs::hard_link(&cache_path, &snapshot).unwrap();

    let replacement = check(&url, &cache_path, DEFAULT_CACHE_TTL, true, 2_000);
    server.join().unwrap();
    assert!(
        replacement.error.is_none(),
        "replacement fetch failed: {replacement:?}"
    );
    let replacement_file = fs::metadata(&cache_path).unwrap();
    let snapshot_bytes = fs::read(snapshot).unwrap();
    let mut actual = Actual {
        requests: 2,
        tag: replacement.release.map(|release| release.tag_name),
        error: replacement.error.is_some(),
        cache_exists: cache_path.exists(),
        cache_bytes: Some(normalize_timestamp(&fs::read(&cache_path).unwrap())),
        timestamp: None,
        cache_mode: None,
        directory_mode: None,
        atomic_replace: file_identity_changed(&initial_file, &replacement_file),
        hardlink_preserved: Some(snapshot_bytes == initial_bytes),
    };
    let bytes = fs::read(&cache_path).unwrap();
    actual.timestamp = Some(cache_timestamp(&bytes));
    set_modes(&mut actual, &cache_path);
    actual
}

fn serve(responses: Vec<(u16, String)>) -> (String, thread::JoinHandle<()>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let server = thread::spawn(move || {
        for (status, body) in responses {
            let (mut stream, _) = listener.accept().unwrap();
            let mut request = [0; 2048];
            let _ = stream.read(&mut request);
            let reason = if status == 200 {
                "OK"
            } else {
                "Internal Server Error"
            };
            write!(
                stream,
                "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            )
            .unwrap();
        }
    });
    (url, server)
}

fn normalize_timestamp(raw: &[u8]) -> String {
    const MARKER: &[u8] = b"\"timestamp\":\"";
    let start = raw
        .windows(MARKER.len())
        .position(|window| window == MARKER)
        .expect("cache JSON has timestamp field");
    let value_start = start + MARKER.len();
    let value_end = value_start
        + raw[value_start..]
            .iter()
            .position(|byte| *byte == b'"')
            .expect("timestamp is terminated");
    assert!(
        !raw[value_end + 1..]
            .windows(MARKER.len())
            .any(|window| window == MARKER),
        "cache JSON has one timestamp field"
    );
    let mut normalized = Vec::with_capacity(raw.len() - (value_end - value_start) + 10);
    normalized.extend_from_slice(&raw[..value_start]);
    normalized.extend_from_slice(b"<TIMESTAMP>");
    normalized.extend_from_slice(&raw[value_end..]);
    String::from_utf8(normalized).unwrap()
}

fn cache_timestamp(raw: &[u8]) -> String {
    const MARKER: &[u8] = b"\"timestamp\":\"";
    let start = raw
        .windows(MARKER.len())
        .position(|window| window == MARKER)
        .expect("cache JSON has timestamp field")
        + MARKER.len();
    let end = start
        + raw[start..]
            .iter()
            .position(|byte| *byte == b'"')
            .expect("timestamp is terminated");
    String::from_utf8(raw[start..end].to_vec()).unwrap()
}

#[cfg(unix)]
fn set_modes(actual: &mut Actual, cache_path: &std::path::Path) {
    use std::os::unix::fs::PermissionsExt;
    actual.cache_mode = Some(fs::metadata(cache_path).unwrap().permissions().mode() & 0o777);
    actual.directory_mode = Some(
        fs::metadata(cache_path.parent().unwrap())
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
    );
}

#[cfg(not(unix))]
fn set_modes(_: &mut Actual, _: &std::path::Path) {}

#[cfg(unix)]
fn file_identity_changed(before: &fs::Metadata, after: &fs::Metadata) -> Option<bool> {
    use std::os::unix::fs::MetadataExt;
    Some(before.ino() != after.ino())
}

// Windows file_index is unstable on the pinned Rust toolchain. The portable
// hardlink observation still proves the old inode's content was not truncated.
#[cfg(not(unix))]
fn file_identity_changed(_: &fs::Metadata, _: &fs::Metadata) -> Option<bool> {
    None
}
