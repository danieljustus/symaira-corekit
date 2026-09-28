//! Byte-exact Go/Rust SSE streaming parity for the public `llmkit` client.
//!
//! Every case here replays a recording captured from Go's
//! `llmkit.Client.StreamChat` by `scripts/rust-port/llm-oracle/main.go` and
//! committed in `testdata/rust-port/fixtures/llm/go-oracle.json`: the wire
//! request (path, query, auth header, provider version, JSON body), the raw
//! response bytes (verified by SHA-256 and length), the callback event order,
//! the finish reason, and any `llmkit` error code and message.
//!
//! Both transports are replayed: the blocking `ureq` stream and the
//! cancellable `reqwest` stream (`stream_chat_cancellable`), so the async
//! injection path cannot drift from the Go-recorded behaviour.

use serde::Deserialize;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;
use symaira_core_llm::{CancellationToken, ChatOptions, Client, ClientBuilder, Message, lookup};

const FIXTURE: &str = include_str!("../../../testdata/rust-port/fixtures/llm/go-oracle.json");

#[derive(Deserialize)]
struct RecordedRequest {
    path: String,
    #[serde(default)]
    query: String,
    auth_header: String,
    #[serde(default)]
    provider_version: String,
    body: Value,
}

#[derive(Debug, Deserialize)]
struct RecordedError {
    code: String,
    error: String,
}

#[derive(Deserialize)]
struct StreamCase {
    kind: String,
    request: RecordedRequest,
    #[serde(default)]
    response: Option<String>,
    response_bytes: usize,
    response_sha256: String,
    deltas: Vec<String>,
    events: Vec<String>,
    finish: String,
    finished: bool,
    error: Option<RecordedError>,
}

#[derive(Deserialize)]
struct StreamErrors {
    no_data: StreamCase,
    bad_chunk: StreamCase,
    oversized_first: StreamCase,
    oversized_after: StreamCase,
}

#[derive(Deserialize)]
struct Fixture {
    openai_stream: StreamCase,
    anthropic_stream: StreamCase,
    openai_stream_errors: StreamErrors,
}

fn fixture() -> Fixture {
    serde_json::from_str(FIXTURE).expect("valid Go oracle fixture")
}

/// Rebuild the raw SSE body Go observed. Small recordings ship inline; the
/// oversized scanner cases are stored as kind + length + SHA-256 only, so the
/// multi-megabyte payloads are regenerated here and re-hashed before replay.
fn response_for(case: &StreamCase) -> String {
    if let Some(response) = &case.response {
        return response.clone();
    }
    let first_chunk = "data: {\"choices\":[{\"delta\":{\"content\":\"first\"}}]}\n\n";
    let oversized = format!("data: {}\n", "x".repeat(1024 * 1024 + 1));
    match case.kind.as_str() {
        "openai_stream_oversized_first" => oversized,
        "openai_stream_oversized_after" => format!("{first_chunk}{oversized}"),
        other => panic!("no response builder for recorded kind {other}"),
    }
}

fn sha256_hex(input: &str) -> String {
    Sha256::digest(input.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn serve(response: String) -> (String, thread::JoinHandle<(String, String)>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut chunk = [0_u8; 4096];
        let mut header_end = None;
        loop {
            let n = stream.read(&mut chunk).unwrap();
            if n == 0 {
                break;
            }
            request.extend_from_slice(&chunk[..n]);
            if let Some(index) = request.windows(4).position(|window| window == b"\r\n\r\n") {
                header_end = Some(index + 4);
                break;
            }
        }
        let header_end = header_end.unwrap();
        let headers = String::from_utf8_lossy(&request[..header_end]).into_owned();
        let content_length = headers
            .lines()
            .find_map(|line| {
                let (name, value) = line.split_once(':')?;
                name.eq_ignore_ascii_case("content-length")
                    .then(|| value.trim().parse::<usize>().ok())
                    .flatten()
            })
            .unwrap_or(0);
        while request.len() < header_end + content_length {
            let n = stream.read(&mut chunk).unwrap();
            if n == 0 {
                break;
            }
            request.extend_from_slice(&chunk[..n]);
        }
        let body = String::from_utf8_lossy(&request[header_end..]).into_owned();
        let bytes = response.as_bytes();
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            bytes.len()
        )
        .unwrap();
        stream.write_all(bytes).unwrap();
        (headers, body)
    });
    (format!("http://{address}"), handle)
}

fn header_value<'a>(headers: &'a str, name: &str) -> Option<&'a str> {
    headers.lines().find_map(|line| {
        let (key, value) = line.split_once(':')?;
        key.eq_ignore_ascii_case(name).then(|| value.trim())
    })
}

#[derive(Debug)]
struct Observed {
    path: String,
    query: String,
    auth_header: String,
    provider_version: String,
    body: Value,
    events: Vec<String>,
    error: Option<(String, String)>,
}

impl Observed {
    fn assert_matches(&self, case: &StreamCase) {
        assert_eq!(self.path, case.request.path, "{} path", case.kind);
        assert_eq!(self.query, case.request.query, "{} query", case.kind);
        assert_eq!(
            self.auth_header, case.request.auth_header,
            "{} auth header",
            case.kind
        );
        assert_eq!(
            self.provider_version, case.request.provider_version,
            "{} provider version",
            case.kind
        );
        assert_eq!(self.body, case.request.body, "{} request body", case.kind);
        assert_eq!(
            self.events, case.events,
            "{} callback event order",
            case.kind
        );
        match (&self.error, &case.error) {
            (None, None) => {}
            (Some((code, message)), Some(recorded)) => {
                assert_eq!(code, &recorded.code, "{} error code", case.kind);
                assert_eq!(message, &recorded.error, "{} error message", case.kind);
            }
            (observed, recorded) => panic!(
                "{} error mismatch: observed {observed:?} recorded {recorded:?}",
                case.kind
            ),
        }
    }
}

fn options_for(case: &StreamCase) -> Option<ChatOptions> {
    match case.kind.as_str() {
        "openai_stream_ok" | "anthropic_stream_ok" => Some(ChatOptions {
            temperature: Some(0.5),
            max_tokens: 64,
            system: "system prompt".into(),
            ..ChatOptions::default()
        }),
        _ => None,
    }
}

fn model_for(case: &StreamCase) -> String {
    case.request.body["model"].as_str().unwrap().to_owned()
}

fn client_for(provider: &str, url: &str) -> Client {
    let base_url = if provider == "openai" {
        format!("{url}/v1")
    } else {
        url.to_owned()
    };
    ClientBuilder::new(lookup(provider).unwrap().clone(), "")
        .base_url(base_url)
        .api_key("dummy-key")
        .async_client(reqwest::Client::builder().build().unwrap())
        .build()
        .unwrap()
}

/// Replay one recording through the blocking stream transport.
fn replay_blocking(provider: &str, case: &StreamCase) -> Observed {
    let response = response_for(case);
    assert_eq!(
        response.len(),
        case.response_bytes,
        "{} response byte count",
        case.kind
    );
    assert_eq!(
        sha256_hex(&response),
        case.response_sha256,
        "{} response sha256",
        case.kind
    );
    let (url, handle) = serve(response);
    let client = client_for(provider, &url);
    let options = options_for(case);
    let model = model_for(case);
    let messages = [Message {
        role: "user".into(),
        content: "question".into(),
    }];
    let deltas: RefCell<Vec<String>> = RefCell::new(Vec::new());
    let events: RefCell<Vec<String>> = RefCell::new(Vec::new());
    let finish: RefCell<String> = RefCell::new(String::new());
    let finished = RefCell::new(false);
    let result = client.stream_chat(
        &model,
        &messages,
        options.as_ref(),
        |delta| {
            deltas.borrow_mut().push(delta.to_owned());
            events.borrow_mut().push(format!("delta:{}", delta));
            Ok(())
        },
        |reason| {
            *finish.borrow_mut() = reason.to_owned();
            *finished.borrow_mut() = true;
            events.borrow_mut().push(format!("finish:{reason}"));
        },
    );
    let (headers, body) = handle.join().unwrap();
    let auth_header = if header_value(&headers, "authorization")
        .is_some_and(|value| value.starts_with("Bearer "))
    {
        "bearer"
    } else if header_value(&headers, "x-api-key").is_some() {
        "x-api-key"
    } else {
        ""
    };
    let target = headers
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .expect("request target");
    let (path, query) = match target.split_once('?') {
        Some((path, query)) => (path.to_owned(), query.to_owned()),
        None => (target.to_owned(), String::new()),
    };
    Observed {
        path,
        query,
        auth_header: auth_header.to_owned(),
        provider_version: header_value(&headers, "anthropic-version")
            .unwrap_or_default()
            .to_owned(),
        body: serde_json::from_str(&body).expect("JSON request body"),
        events: events.into_inner(),
        error: result
            .err()
            .map(|error| (error.code.as_str().to_owned(), error.to_string())),
    }
}

/// Replay the same recording through the cancellable async stream transport.
fn replay_cancellable(provider: &str, case: &StreamCase) -> Observed {
    let response = response_for(case);
    let (url, handle) = serve(response);
    let client = client_for(provider, &url);
    let options = options_for(case);
    let model = model_for(case);
    let messages = [Message {
        role: "user".into(),
        content: "question".into(),
    }];
    let token = CancellationToken::new();
    let deltas: RefCell<Vec<String>> = RefCell::new(Vec::new());
    let events: RefCell<Vec<String>> = RefCell::new(Vec::new());
    let finish: RefCell<String> = RefCell::new(String::new());
    let finished = RefCell::new(false);
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();
    let result = runtime.block_on(async {
        client
            .stream_chat_cancellable(
                &token,
                &model,
                &messages,
                options.as_ref(),
                |delta| {
                    deltas.borrow_mut().push(delta.to_owned());
                    events.borrow_mut().push(format!("delta:{}", delta));
                    Ok(())
                },
                |reason| {
                    *finish.borrow_mut() = reason.to_owned();
                    *finished.borrow_mut() = true;
                    events.borrow_mut().push(format!("finish:{reason}"));
                },
            )
            .await
    });
    let (headers, body) = handle.join().unwrap();
    let auth_header = if header_value(&headers, "authorization")
        .is_some_and(|value| value.starts_with("Bearer "))
    {
        "bearer"
    } else if header_value(&headers, "x-api-key").is_some() {
        "x-api-key"
    } else {
        ""
    };
    let target = headers
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .expect("request target");
    let (path, query) = match target.split_once('?') {
        Some((path, query)) => (path.to_owned(), query.to_owned()),
        None => (target.to_owned(), String::new()),
    };
    Observed {
        path,
        query,
        auth_header: auth_header.to_owned(),
        provider_version: header_value(&headers, "anthropic-version")
            .unwrap_or_default()
            .to_owned(),
        body: serde_json::from_str(&body).expect("JSON request body"),
        events: events.into_inner(),
        error: result
            .err()
            .map(|error| (error.code.as_str().to_owned(), error.to_string())),
    }
}

fn assert_recorded_deltas(case: &StreamCase, observed: &Observed) {
    let deltas: Vec<String> = observed
        .events
        .iter()
        .filter_map(|event| event.strip_prefix("delta:").map(str::to_owned))
        .collect();
    assert_eq!(deltas, case.deltas, "{} deltas", case.kind);
    let finish: Vec<&str> = observed
        .events
        .iter()
        .filter_map(|event| event.strip_prefix("finish:"))
        .collect();
    if case.finished {
        assert_eq!(
            finish,
            [case.finish.as_str()],
            "{} finish events",
            case.kind
        );
    } else {
        assert!(finish.is_empty(), "{} unexpected finish event", case.kind);
    }
}

fn replay_both(provider: &str, case: &StreamCase) {
    let blocking = replay_blocking(provider, case);
    blocking.assert_matches(case);
    let cancellable = replay_cancellable(provider, case);
    cancellable.assert_matches(case);
    assert_recorded_deltas(case, &blocking);
    assert_recorded_deltas(case, &cancellable);
}

#[test]
fn go_recorded_stream_wire_and_callback_order_match() {
    let fixture = fixture();
    replay_both("openai", &fixture.openai_stream);
    replay_both("anthropic", &fixture.anthropic_stream);
}

#[test]
fn go_recorded_malformed_stream_errors_match() {
    let fixture = fixture();
    let errors = &fixture.openai_stream_errors;
    for case in [
        &errors.no_data,
        &errors.bad_chunk,
        &errors.oversized_first,
        &errors.oversized_after,
    ] {
        replay_both("openai", case);
    }
}
