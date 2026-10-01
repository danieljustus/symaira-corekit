#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::collections::HashSet;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;
use symaira_core_llm::{CancellationToken, ClientBuilder, Message, lookup};

const EXPECTED_OPENAI_SUCCESS_CASES: usize = 29;

fn mock_server(response: &str) -> (String, thread::JoinHandle<()>) {
    let response = response.to_owned();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut chunk = [0_u8; 4096];
        let header_end = loop {
            let count = stream.read(&mut chunk).unwrap();
            assert_ne!(count, 0, "client closed before request headers");
            request.extend_from_slice(&chunk[..count]);
            if let Some(index) = request.windows(4).position(|window| window == b"\r\n\r\n") {
                break index + 4;
            }
        };
        let headers = String::from_utf8_lossy(&request[..header_end]);
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
            let count = stream.read(&mut chunk).unwrap();
            assert_ne!(count, 0, "client closed before request body");
            request.extend_from_slice(&chunk[..count]);
        }
        write!(
            stream,
            "HTTP/1.1 200 Test\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
            response.len()
        )
        .unwrap();
        stream.write_all(response.as_bytes()).unwrap();
    });
    (format!("http://{address}/v1"), handle)
}

fn fixture() -> Value {
    serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap()
}

fn assert_fixture_case(case: &Value, cancellable: bool, runtime: &tokio::runtime::Runtime) {
    let (url, server) = mock_server(case["body"].as_str().unwrap());
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .build()
        .unwrap();
    let messages = [Message {
        role: "user".into(),
        content: "question".into(),
    }];
    let result = if cancellable {
        runtime.block_on(client.chat_cancellable(
            &CancellationToken::new(),
            "gpt-5",
            &messages,
            None,
        ))
    } else {
        client.chat("gpt-5", &messages, None)
    };
    server.join().unwrap();

    let case_id = case["id"].as_str().unwrap();
    match case["kind"].as_str().unwrap() {
        "success" => {
            let choice = result.unwrap_or_else(|error| {
                panic!("{case_id} ({cancellable}): unexpected error: {error}")
            });
            assert_eq!(
                choice.content,
                case["content"].as_str().unwrap_or_default(),
                "{case_id}"
            );
            assert_eq!(
                choice.finish_reason,
                case["finish_reason"].as_str().unwrap_or_default(),
                "{case_id}"
            );
            let expected_calls: Vec<Value> = case
                .get("tool_calls")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .map(|call| {
                    // The Go oracle records RawMessage bytes; Rust exposes parsed JSON,
                    // falling back to the original string when the bytes are not JSON.
                    let raw = call["arguments_raw"].as_str().unwrap_or_default();
                    let arguments =
                        serde_json::from_str(raw).unwrap_or_else(|_| Value::String(raw.to_owned()));
                    json!({"id":call["id"], "name":call["name"], "arguments":arguments})
                })
                .collect();
            assert_eq!(
                serde_json::to_value(choice.tool_calls).unwrap(),
                json!(expected_calls),
                "{case_id}"
            );
        }
        "error" => {
            let error = result
                .err()
                .unwrap_or_else(|| panic!("{case_id} ({cancellable}): expected an error"));
            assert_eq!(error.code.as_str(), case["error_code"], "{case_id}");
        }
        kind => panic!("unknown fixture kind {kind}"),
    }
}

#[test]
fn openai_success_responses_match_go_for_sync_and_cancellable_clients() {
    let fixture = fixture();
    let cases = fixture["openai_success_responses"].as_array().unwrap();
    assert_eq!(cases.len(), EXPECTED_OPENAI_SUCCESS_CASES);
    let case_ids: Vec<&str> = cases
        .iter()
        .map(|case| case["id"].as_str().unwrap())
        .collect();
    assert_eq!(
        case_ids.iter().copied().collect::<HashSet<_>>().len(),
        EXPECTED_OPENAI_SUCCESS_CASES,
        "fixture case IDs must be unique"
    );
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    for case in cases {
        assert_fixture_case(case, false, &runtime);
        assert_fixture_case(case, true, &runtime);
    }
}
