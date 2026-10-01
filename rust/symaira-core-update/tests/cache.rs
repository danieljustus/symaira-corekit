use serde::{Deserialize, Serialize};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::Duration,
};
use symaira_core_update::cache::{DEFAULT_CACHE_TTL, Outcome, check};

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
struct Fixture {
    default_cache_ttl_seconds: u64,
    cases: Vec<Case>,
}
#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
struct Case {
    id: String,
    requests: usize,
    result: ResultValue,
}
#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
struct ResultValue {
    release: Option<String>,
    error: bool,
}

fn observation(id: &str, requests: usize, outcome: Outcome) -> Case {
    Case {
        id: id.into(),
        requests,
        result: ResultValue {
            release: outcome.release.map(|r| r.tag_name),
            error: outcome.error.is_some(),
        },
    }
}

#[test]
fn persistent_cache_force_expiry_and_failed_refresh_match_go_fixture() {
    let fixture: Fixture = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/update/cache.json"
    ))
    .unwrap();
    assert_eq!(
        fixture.default_cache_ttl_seconds,
        DEFAULT_CACHE_TTL.as_secs()
    );
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}/releases/latest", listener.local_addr().unwrap());
    let responses = [
        (200, r#"{"tag_name":"v1.2.0","body":"initial"}"#),
        (200, r#"{"tag_name":"v1.3.0","body":"forced"}"#),
        (200, r#"{"tag_name":"v1.4.0","body":"expired"}"#),
        (500, r#"{"message":"temporary failure"}"#),
    ];
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
            write!(stream, "HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
        }
    });
    let path = std::env::temp_dir().join(format!("upd003-cache-{}.json", std::process::id()));
    let _ = std::fs::remove_file(&path);
    let ttl = DEFAULT_CACHE_TTL;
    let cases = vec![
        observation("initial-fetch", 1, check(&url, &path, ttl, false, 1_000)),
        observation("cache-hit", 1, check(&url, &path, ttl, false, 1_001)),
        observation("forced-refresh", 2, check(&url, &path, ttl, true, 1_002)),
        observation(
            "cache-after-force",
            2,
            check(&url, &path, ttl, false, 1_003),
        ),
        observation(
            "expired-fetch",
            3,
            check(&url, &path, Duration::ZERO, false, 1_004),
        ),
        observation(
            "expired-refresh-failure",
            4,
            check(&url, &path, Duration::ZERO, false, 1_005),
        ),
        observation(
            "persistent-across-checkers",
            4,
            check(&url, &path, ttl, false, 1_006),
        ),
    ];
    server.join().unwrap();
    let _ = std::fs::remove_file(&path);
    assert_eq!(cases, fixture.cases);
}
