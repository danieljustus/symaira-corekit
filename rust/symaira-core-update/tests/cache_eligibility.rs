use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
};
use symaira_core_update::cache::{DEFAULT_CACHE_TTL, check};

#[test]
fn network_eligibility_is_checked_before_persistence() {
    for (id, body, error) in [
        (
            "stable",
            r#"{"tag_name":"v1.3.0","draft":false,"prerelease":false}"#,
            None,
        ),
        (
            "draft",
            r#"{"tag_name":"v1.3.0","draft":true}"#,
            Some("latest release response returned a draft release"),
        ),
        (
            "prerelease",
            r#"{"tag_name":"v1.3.0","prerelease":true}"#,
            Some("latest release response returned a prerelease"),
        ),
        (
            "invalid",
            r#"{"tag_name":"not-a-version"}"#,
            Some("latest release tag \"not-a-version\" is not a stable semantic version"),
        ),
        (
            "tag-prerelease",
            r#"{"tag_name":"v1.3.0-rc.1"}"#,
            Some("latest release tag \"v1.3.0-rc.1\" is not a stable semantic version"),
        ),
    ] {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            let _ = stream.read(&mut [0; 2048]);
            write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                body.len()
            )
            .unwrap();
        });
        let path = std::env::temp_dir().join(format!(
            "cache-eligibility-{}-{id}.json",
            std::process::id()
        ));
        assert!(!path.exists(), "test requires a fresh cache");
        let outcome = check(&url, &path, DEFAULT_CACHE_TTL, false, 1_000);
        server.join().unwrap();
        assert_eq!(outcome.error.as_deref(), error, "{id}");
        if error.is_some() {
            assert!(outcome.release.is_none(), "{id}");
            assert!(!path.exists(), "ineligible response persisted: {id}");
            let replay = check(&url, &path, DEFAULT_CACHE_TTL, false, 1_001);
            assert!(replay.release.is_none(), "ineligible cache replay: {id}");
            assert!(replay.error.is_some());
        } else {
            assert_eq!(outcome.release.unwrap().tag_name, "v1.3.0");
            let disk: serde_json::Value =
                serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            assert_eq!(disk["release"]["TagName"], "v1.3.0");
            assert!(disk["release"].get("draft").is_none());
            let replay = check(&url, &path, DEFAULT_CACHE_TTL, false, 1_001);
            assert_eq!(replay.release.unwrap().tag_name, "v1.3.0");
            assert!(replay.error.is_none());
            std::fs::remove_file(path).unwrap();
        }
    }
}
