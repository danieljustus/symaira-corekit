use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
};
use symaira_core_update::cache::{DEFAULT_CACHE_TTL, check};

#[test]
fn repeated_assets_preserve_existing_elements_and_reset_arrays() {
    for (id, assignments, expected) in [
        (
            "shrink-grow",
            r#"[{"name":"short"}],"assets":[{},{}]"#,
            serde_json::json!([
                {"Name":"short","BrowserDownloadURL":"url","Size":7},
                {"Name":"second","BrowserDownloadURL":"","Size":8}
            ]),
        ),
        (
            "omitted",
            r#"[{"name":"new"},null,{"name":"added"}]"#,
            serde_json::json!([
                {"Name":"new","BrowserDownloadURL":"url","Size":7},
                {"Name":"second","BrowserDownloadURL":"","Size":8},
                {"Name":"added","BrowserDownloadURL":"","Size":0}
            ]),
        ),
        (
            "scalar-null",
            r#"[{"name":null,"size":null,"browser_download_url":null}]"#,
            serde_json::json!([
                {"Name":"old","BrowserDownloadURL":"url","Size":7}
            ]),
        ),
        ("empty", "[]", serde_json::json!([])),
        ("null", "null", serde_json::json!([])),
        (
            "empty-reset",
            "[],\"assets\":[{\"name\":\"new\"}]",
            serde_json::json!([
                {"Name":"new","BrowserDownloadURL":"","Size":0}
            ]),
        ),
        (
            "null-reset",
            "null,\"assets\":[{\"name\":\"new\"}]",
            serde_json::json!([
                {"Name":"new","BrowserDownloadURL":"","Size":0}
            ]),
        ),
    ] {
        let body = format!(
            r#"{{"tag_name":"v1.3.0","assets":[{{"name":"old","size":7,"browser_download_url":"url"}},{{"name":"second","size":8}}],"ASSETS":{assignments}}}"#
        );
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
        let path =
            std::env::temp_dir().join(format!("cache-assets-{}-{id}.json", std::process::id()));
        assert!(!path.exists());
        let outcome = check(&url, &path, DEFAULT_CACHE_TTL, false, 1_000);
        server.join().unwrap();
        assert!(outcome.error.is_none(), "{id}: {outcome:?}");
        let disk: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        assert_eq!(disk["release"]["Assets"], expected, "API {id}");

        // Exercise the same ordered decoder through the public disk-cache path.
        let disk_assignments = assignments
            .replace("name", "Name")
            .replace("size", "Size")
            .replace("browser_download_url", "BrowserDownloadURL")
            .replace("assets", "Assets");
        std::fs::write(&path, format!(r#"{{"timestamp":"1970-01-01T00:00:01Z","release":{{"TagName":"v1.3.0","Assets":[{{"Name":"old","Size":7,"BrowserDownloadURL":"url"}},{{"Name":"second","Size":8}}],"ASSETS":{disk_assignments}}}}}"#)).unwrap();
        let replay = check(&url, &path, DEFAULT_CACHE_TTL, false, 1_001);
        assert!(replay.error.is_none(), "disk {id}: {replay:?}");
        let response: serde_json::Value =
            serde_json::from_str(&replay.release.unwrap().response).unwrap();
        let actual = response["Assets"]
            .as_array()
            .into_iter()
            .flatten()
            .map(|asset| {
                serde_json::json!({
                    "Name":asset["Name"].as_str().unwrap_or_default(),
                    "BrowserDownloadURL":asset["BrowserDownloadURL"].as_str().unwrap_or_default(),
                    "Size":asset["Size"].as_i64().unwrap_or_default()
                })
            })
            .collect::<Vec<_>>();
        assert_eq!(serde_json::json!(actual), expected, "disk {id}");
        std::fs::remove_file(path).unwrap();
    }
}

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
            "draft-alias",
            r#"{"tag_name":"v1.3.0","DRAFT":false,"draft":true}"#,
            Some("latest release response returned a draft release"),
        ),
        (
            "draft-alias-valid",
            r#"{"tag_name":"v1.3.0","draft":true,"DRAFT":false,"draft":null}"#,
            None,
        ),
        (
            "prerelease-alias",
            r#"{"tag_name":"v1.3.0","PRERELEASE":false,"prerelease":true}"#,
            Some("latest release response returned a prerelease"),
        ),
        (
            "tag-alias-invalid",
            r#"{"TAG_NAME":"v1.3.0","tag_name":"not-a-version"}"#,
            Some("latest release tag \"not-a-version\" is not a stable semantic version"),
        ),
        (
            "tag-alias-valid",
            r#"{"TAG_NAME":"not-a-version","tag_name":"v1.3.0","TAG_NAME":null}"#,
            None,
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
            let release = outcome.release.unwrap();
            assert_eq!(release.tag_name, "v1.3.0");
            assert_eq!(
                release.response, body,
                "API response bytes must be retained"
            );
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
