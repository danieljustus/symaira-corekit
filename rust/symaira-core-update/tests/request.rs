use serde::Deserialize;
use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread;
use std::time::Duration;
use symaira_core_update::request::{fetch, is_github_host};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    url_after_trim: Option<String>,
    request_line: Option<String>,
    headers: Option<BTreeMap<String, String>>,
    response_headers: Option<BTreeMap<String, String>>,
    status: Option<u16>,
    error_code: Option<String>,
    error_message: Option<String>,
}

fn fixture() -> Fixture {
    let path = std::env::var("UPDATE_REQUEST_FIXTURE").unwrap_or_else(|_| {
        concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../testdata/rust-port/fixtures/update/requests.json"
        )
        .into()
    });
    serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap()
}

fn go<'a>(fixture: &'a Fixture, id: &str) -> &'a Case {
    fixture.cases.iter().find(|case| case.id == id).unwrap()
}

fn serve(status: u16, body: &'static str, delay: Duration) -> (String, thread::JoinHandle<String>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let request = read_headers(&mut stream);
        if !delay.is_zero() {
            thread::sleep(delay);
        }
        let response = format!(
            "HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n{}\r\n{}",
            body.len(),
            if status == 429 {
                "Retry-After: 17\r\n"
            } else {
                ""
            },
            body
        );
        let _ = stream.write_all(response.as_bytes());
        request
    });
    (format!("http://{address}"), handle)
}

fn read_headers(stream: &mut TcpStream) -> String {
    let mut data = Vec::new();
    let mut byte = [0];
    while !data.ends_with(b"\r\n\r\n") {
        if stream.read_exact(&mut byte).is_err() {
            break;
        }
        data.push(byte[0]);
    }
    String::from_utf8_lossy(&data).into_owned()
}

fn request_headers(raw: &str) -> BTreeMap<String, String> {
    let mut headers = BTreeMap::new();
    for line in raw.lines().skip(1) {
        let Some((key, value)) = line.split_once(':') else {
            continue;
        };
        let value = value.trim();
        let value = if key.eq_ignore_ascii_case("Host") {
            format!(
                "{}:<port>",
                value.rsplit_once(':').map_or(value, |(host, _)| host)
            )
        } else {
            value.to_owned()
        };
        let key = match key.to_ascii_lowercase().as_str() {
            "accept" => "Accept",
            "accept-encoding" => "Accept-Encoding",
            "host" => "Host",
            "user-agent" => "User-Agent",
            _ => key,
        };
        headers.insert(key.to_owned(), value);
    }
    headers.insert("If-None-Match".into(), String::new());
    headers
}

#[test]
fn update_request_and_errors_match_go_oracle() {
    let fixture = fixture();
    assert_eq!(fixture.cases.len(), 11);

    let (base, request) = serve(200, r#"{"tag_name":"v1.2.4"}"#, Duration::ZERO);
    let url = format!("  {base}/request?x=1  ");
    let response = fetch(&url, " 1.2.3 ", Duration::from_secs(2)).unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(&response.body).unwrap()["tag_name"],
        "v1.2.4"
    );
    let request = request.join().unwrap();
    let expected = go(&fixture, "request");
    assert_eq!(request.lines().next(), expected.request_line.as_deref());
    assert_eq!(
        request_headers(&request),
        *expected.headers.as_ref().unwrap()
    );
    assert_eq!(expected.status, Some(response.status));
    assert_eq!(expected.error_code, None);
    assert!(
        expected
            .url_after_trim
            .as_deref()
            .unwrap()
            .ends_with("/request?x=1")
    );

    for (id, status, body, code) in [
        ("404", 404, "not found", "http_404"),
        ("429-retry-after", 429, "rate limited", "http_429"),
        ("malformed-json", 200, r#"{"tag_name":"#, "malformed_json"),
    ] {
        let (base, server) = serve(status, body, Duration::ZERO);
        let expected = go(&fixture, id);
        let result = fetch(&base, "1.2.3", Duration::from_secs(2));
        let message = if id == "malformed-json" {
            let response = result.unwrap();
            assert!(serde_json::from_slice::<serde_json::Value>(&response.body).is_err());
            "decode latest release response: unexpected EOF".to_owned()
        } else {
            let error = result.unwrap_err();
            assert_eq!(error.code, code, "{id}");
            error.message
        };
        assert_eq!(expected.error_code.as_deref(), Some(code), "{id}");
        assert_eq!(
            expected.error_message.as_deref(),
            Some(message.as_str()),
            "{id}"
        );
        assert_eq!(expected.status, Some(status));
        if id == "429-retry-after" {
            assert_eq!(
                expected.response_headers.as_ref().unwrap()["Retry-After"],
                "17"
            );
        }
        let _ = server.join();
    }

    let (base, server) = serve(200, r#"{"tag_name":"v1.2.4"}"#, Duration::from_millis(120));
    let error = fetch(&base, "1.2.3", Duration::from_millis(30)).unwrap_err();
    assert_eq!(error.code, "timeout");
    assert_eq!(
        error.message,
        go(&fixture, "timeout").error_message.as_deref().unwrap()
    );
    let _ = server.join();

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    drop(listener);
    // A freed loopback port is normally refused at once, but a host may filter it
    // instead. Probe what THIS host does and require Rust to classify that same
    // outcome: the assertion is then environment evidence, not a hardcoded string.
    let host_refuses = matches!(
        std::net::TcpStream::connect_timeout(&address, Duration::from_millis(500)),
        Err(error) if error.kind() == std::io::ErrorKind::ConnectionRefused
    );
    let expected = if host_refuses {
        "connection_refused"
    } else {
        "timeout"
    };
    let error = fetch(
        &format!("http://{address}/refused"),
        "1.2.3",
        Duration::from_secs(2),
    )
    .unwrap_err();
    assert_eq!(
        error.code,
        expected,
        "freed loopback port: host_refuses={host_refuses}, fixture={}",
        go(&fixture, "connection-refused")
            .error_code
            .as_deref()
            .unwrap()
    );
    assert_eq!(
        error.message,
        go(&fixture, "connection-refused")
            .error_message
            .as_deref()
            .unwrap()
    );
}

#[test]
fn secure_redirect_policy_matches_go_oracle() {
    let fixture = fixture();
    assert_eq!(
        go(&fixture, "secure-client").error_code.as_deref(),
        Some("tls_minimum")
    );
    assert_eq!(
        go(&fixture, "tls-certificate").error_code.as_deref(),
        Some("tls_certificate")
    );
    if let Ok(tls_url) = std::env::var("UPDATE_REQUEST_TLS_URL") {
        let error = fetch(&tls_url, "1.2.3", Duration::from_secs(2)).unwrap_err();
        assert_eq!(error.code, "tls_certificate");
        assert_eq!(
            error.message,
            go(&fixture, "tls-certificate")
                .error_message
                .as_deref()
                .unwrap()
        );
    }
    for host in [
        "github.com",
        "api.github.com",
        "assets.github.com",
        "objects.githubusercontent.com",
    ] {
        assert!(is_github_host(host), "{host}");
    }
    for host in ["evil.example", "notgithub.com", "github.com.evil.example"] {
        assert!(!is_github_host(host), "{host}");
    }
    assert_eq!(
        go(&fixture, "redirect-foreign").error_code.as_deref(),
        Some("refused")
    );
    assert_eq!(
        go(&fixture, "redirect-github").error_code.as_deref(),
        Some("allowed")
    );
    assert_eq!(
        go(&fixture, "redirect-cap").error_code.as_deref(),
        Some("refused")
    );
}
