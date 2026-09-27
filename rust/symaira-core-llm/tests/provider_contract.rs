#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;
use std::time::Duration;
use symaira_core_exit::ExitCode;
use symaira_core_llm::{
    Agent, AuthScheme, CancellationToken, ChatOptions, ClientBuilder, DEFAULT_TIMEOUT, ErrorCode,
    GenerateOption, Message, NativeChatOption, Tool, WireDialect, lookup, providers,
};
use ureq::Proxy;

fn mock_server(
    status: u16,
    response: impl Into<String>,
) -> (String, thread::JoinHandle<(String, String, String)>) {
    let response = response.into();
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
            if let Some(i) = request.windows(4).position(|w| w == b"\r\n\r\n") {
                header_end = Some(i + 4);
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
        write!(stream, "HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nRetry-After: 17\r\nLocation: http://127.0.0.1:1/redirected\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", bytes.len()).unwrap();
        stream.write_all(bytes).unwrap();
        (headers, body, String::new())
    });
    (format!("http://{address}"), handle)
}

fn mock_connect_proxy(response: &'static str) -> (String, thread::JoinHandle<(String, String)>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let handle = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut chunk = [0_u8; 4096];
        let connect_end = loop {
            let n = stream.read(&mut chunk).unwrap();
            request.extend_from_slice(&chunk[..n]);
            if let Some(i) = request.windows(4).position(|w| w == b"\r\n\r\n") {
                break i + 4;
            }
        };
        let connect = String::from_utf8_lossy(&request[..connect_end]).into_owned();
        stream
            .write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            .unwrap();
        request.clear();
        let request_end = loop {
            let n = stream.read(&mut chunk).unwrap();
            if n == 0 {
                panic!("client closed before sending tunneled request");
            }
            request.extend_from_slice(&chunk[..n]);
            if let Some(i) = request.windows(4).position(|w| w == b"\r\n\r\n") {
                break i + 4;
            }
        };
        let headers = String::from_utf8_lossy(&request[..request_end]).into_owned();
        let bytes = response.as_bytes();
        write!(stream, "HTTP/1.1 200 Test\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n", bytes.len()).unwrap();
        stream.write_all(bytes).unwrap();
        (connect, headers)
    });
    (format!("http://{address}"), handle)
}

fn read_request(stream: &mut std::net::TcpStream) {
    let mut request = Vec::new();
    let mut chunk = [0_u8; 4096];
    let header_end = loop {
        let n = stream.read(&mut chunk).unwrap();
        assert_ne!(n, 0, "client closed before sending request headers");
        request.extend_from_slice(&chunk[..n]);
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
        let n = stream.read(&mut chunk).unwrap();
        assert_ne!(n, 0, "client closed before sending request body");
        request.extend_from_slice(&chunk[..n]);
    }
}

fn server_observes_close(stream: &mut std::net::TcpStream) -> bool {
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    let mut byte = [0_u8; 1];
    matches!(stream.read(&mut byte), Ok(0))
}

#[test]
fn cancellable_chat_preserves_go_openai_wire_contract() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        200,
        r#"{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}"#,
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let choice = runtime
        .block_on(client.chat_cancellable(
            &token,
            "gpt-5",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            Some(&ChatOptions {
                system: "system prompt".into(),
                max_tokens: 32,
                ..ChatOptions::default()
            }),
        ))
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with(&format!(
        "POST {} HTTP/1.1",
        fixture["openai_chat"]["path"].as_str().unwrap()
    )));
    assert!(
        headers
            .lines()
            .any(|line| line.eq_ignore_ascii_case("user-agent: Go-http-client/1.1"))
    );
    let body: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(body, fixture["openai_chat"]["body"]);
    assert_eq!(choice.content, "answer");
    assert_eq!(choice.finish_reason, "stop");
}

#[test]
fn cancellable_api_does_not_silently_ignore_an_injected_agent() {
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .api_key("dummy-key")
        .agent(Agent::new_with_defaults())
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let error = runtime
        .block_on(client.chat_cancellable(
            &token,
            "gpt-5",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            None,
        ))
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::ProviderError);
    assert!(error.detail.contains("cannot use an injected ureq Agent"));
}

#[test]
fn cancellable_chat_preserves_go_rate_limit_and_header_classification() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let token = CancellationToken::new();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let cases = [
        (
            "openai",
            r#"{"error":"busy"}"#,
            ErrorCode::RateLimited,
            429,
            "17",
            true,
        ),
        // Go's openAIErrorFromBody reclassifies a typed 429 as status 400 and
        // rebuilds the error from its message, dropping Retry-After.
        (
            "openai",
            r#"{"error":{"message":"rate limit exceeded","type":"rate_limit_error"}}"#,
            ErrorCode::RateLimited,
            400,
            "",
            true,
        ),
        // Go's Anthropic path returns do's original status/body/header.
        (
            "anthropic",
            r#"{"type":"error","error":{"type":"rate_limit_error","message":"overloaded"}}"#,
            ErrorCode::RateLimited,
            429,
            "17",
            true,
        ),
    ];

    for (provider, body, code, status, retry_after, retryable) in cases {
        let mut observed = Vec::new();
        for cancellable in [false, true] {
            let (url, server) = mock_server(429, body);
            let url = if provider == "openai" {
                format!("{url}/v1")
            } else {
                url
            };
            let client = ClientBuilder::new(lookup(provider).unwrap().clone(), "")
                .base_url(url)
                .api_key("dummy-key")
                .build()
                .unwrap();
            let result = if cancellable {
                runtime.block_on(client.chat_cancellable(
                    &token,
                    "model",
                    &[Message {
                        role: "user".into(),
                        content: "question".into(),
                    }],
                    None,
                ))
            } else {
                client.chat(
                    "model",
                    &[Message {
                        role: "user".into(),
                        content: "question".into(),
                    }],
                    None,
                )
            };
            server.join().unwrap();
            let error = result.unwrap_err();
            assert_eq!(error.code, code, "{provider}, cancellable={cancellable}");
            assert_eq!(
                error.status_code, status,
                "{provider}, cancellable={cancellable}"
            );
            assert_eq!(
                error.retry_after, retry_after,
                "{provider}, cancellable={cancellable}"
            );
            assert_eq!(error.retryable(), retryable);
            observed.push(error);
        }
        assert_eq!(
            observed[0], observed[1],
            "{provider} sync/async error drift"
        );
    }
    assert_eq!(fixture["rate_limit"]["body"], r#"{"error":"busy"}"#);
    assert_eq!(fixture["rate_limit"]["code"], "rate_limited");
    assert_eq!(fixture["rate_limit"]["status"], 429);
    assert_eq!(fixture["rate_limit"]["retry_after"], "17");
    assert_eq!(fixture["rate_limit"]["retryable"], true);

    let messages = [Message {
        role: "user".into(),
        content: "question".into(),
    }];
    let mut invalid_extra_name = lookup("openai").unwrap().clone();
    invalid_extra_name
        .extra_headers
        .insert("invalid header".to_owned(), "value".to_owned());
    let mut invalid_extra_value = lookup("openai").unwrap().clone();
    invalid_extra_value
        .extra_headers
        .insert("x-test".to_owned(), "invalid\nvalue".to_owned());
    let mut invalid_auth_name = lookup("openai").unwrap().clone();
    invalid_auth_name.auth_scheme = AuthScheme::Header;
    invalid_auth_name.auth_header = "invalid header".to_owned();
    let invalid_headers = [
        (invalid_extra_name, "dummy-key", "invalid provider header:"),
        (
            invalid_extra_value,
            "dummy-key",
            "invalid provider header value:",
        ),
        (invalid_auth_name, "dummy-key", "invalid auth header:"),
        (
            lookup("openai").unwrap().clone(),
            "invalid\nkey",
            "invalid auth value:",
        ),
    ];
    for (descriptor, api_key, detail_prefix) in invalid_headers {
        let client = ClientBuilder::new(descriptor, "")
            .api_key(api_key)
            .build()
            .unwrap();
        let sync_error = client
            .chat("model", &messages, None)
            .expect_err("sync transport rejects invalid headers");
        let async_error = runtime
            .block_on(client.chat_cancellable(&token, "model", &messages, None))
            .expect_err("cancellable transport rejects invalid headers");
        assert_eq!(sync_error.code, ErrorCode::ProviderError);
        assert!(sync_error.detail.contains(detail_prefix), "{sync_error:?}");
        assert_eq!(async_error, sync_error);
    }
}

#[test]
fn cancellation_closes_connection_while_waiting_for_response_headers() {
    // Go's net/http request uses the supplied context through Do and returns
    // when that context is cancelled (llmkit/client.go:138-161).
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let (started_tx, started_rx) = std::sync::mpsc::channel();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        read_request(&mut stream);
        started_tx.send(()).unwrap();
        server_observes_close(&mut stream)
    });
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("http://{address}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();
    let worker = runtime.spawn(async move {
        client
            .chat_cancellable(
                &worker_token,
                "gpt-5",
                &[Message {
                    role: "user".into(),
                    content: "question".into(),
                }],
                None,
            )
            .await
    });
    started_rx
        .recv_timeout(Duration::from_secs(2))
        .expect("provider did not receive the request");
    token.cancel();
    let error = runtime.block_on(async {
        tokio::time::timeout(Duration::from_secs(2), worker)
            .await
            .expect("cancelled chat did not return promptly")
            .unwrap()
            .unwrap_err()
    });
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(server.join().unwrap(), "provider connection stayed open");
}

#[test]
fn cancellation_closes_connection_while_waiting_for_next_stream_chunk() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        read_request(&mut stream);
        stream
            .write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: keep-alive\r\n\r\ndata: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n",
            )
            .unwrap();
        stream.flush().unwrap();
        server_observes_close(&mut stream)
    });
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("http://{address}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let (seen_tx, seen_rx) = std::sync::mpsc::channel();
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();
    let worker = runtime.spawn(async move {
        client
            .stream_chat_cancellable(
                &worker_token,
                "gpt-5",
                &[Message {
                    role: "user".into(),
                    content: "question".into(),
                }],
                None,
                |delta| {
                    seen_tx.send(delta.to_owned()).unwrap();
                    Ok(())
                },
                |_| {},
            )
            .await
    });
    assert_eq!(
        seen_rx.recv_timeout(Duration::from_secs(2)).unwrap(),
        "partial"
    );
    token.cancel();
    let error = runtime.block_on(async {
        tokio::time::timeout(Duration::from_secs(2), worker)
            .await
            .expect("cancelled stream did not return promptly")
            .unwrap()
            .unwrap_err()
    });
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(server.join().unwrap(), "provider connection stayed open");
}

#[test]
fn registry_and_go_generated_snapshot_are_available() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(
        serde_json::to_value(providers()).unwrap(),
        fixture["providers"]
    );
    assert_eq!(providers()[0].id, "anthropic");
    assert_eq!(lookup("OPENAI").unwrap().default_model(), "gpt-5");
    assert_eq!(lookup("custom").unwrap().base_url, "");
    assert_eq!(lookup("unknown"), None);
}

#[test]
fn empty_api_key_uses_credential_resolution() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(fixture["empty_api_key_resolves"], true);
    let error = match ClientBuilder::new(lookup("openai").unwrap().clone(), "env://")
        .api_key("")
        .build()
    {
        Ok(_) => panic!("empty API key bypassed credential resolution"),
        Err(error) => error,
    };
    assert_eq!(error.code, ErrorCode::AuthFailure);
}

#[test]
fn injected_default_agent_keeps_provider_error_classification() {
    let (url, server) = mock_server(429, r#"{"error":{"message":"temporary"}}"#);
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .agent(Agent::new_with_defaults())
        .build()
        .unwrap();
    let error = client
        .chat(
            "gpt-5",
            &[Message {
                role: "user".into(),
                content: "hi".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    assert_eq!(error.code, ErrorCode::RateLimited);
    assert_eq!(error.status_code, 429, "{error:?}");
    assert_eq!(error.retry_after, "17");
    assert!(error.body.contains("temporary"));
}

#[test]
fn dialect_override_follows_go_builder_behavior() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(fixture["dialect_override_allowed"], true);
    ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .api_key("dummy-key")
        .dialect(WireDialect::Anthropic)
        .build()
        .unwrap();
}

#[test]
fn zero_timeout_keeps_go_unbounded_request_behavior() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(fixture["zero_timeout_allowed"], true);
    let (url, server) = mock_server(200, r#"{"choices":[{"message":{"content":"answer"}}]}"#);
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .timeout(Duration::ZERO)
        .build()
        .unwrap();
    let result = client.chat(
        "gpt-5",
        &[Message {
            role: "user".into(),
            content: "question".into(),
        }],
        None,
    );
    assert!(result.is_ok(), "zero timeout failed: {result:?}");
    server.join().unwrap();
}

#[test]
fn anthropic_content_includes_text_from_every_block_like_go() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        200,
        r#"{"content":[{"type":"text","text":"first"},{"type":"tool_use","text":"second"}],"stop_reason":"end_turn"}"#,
    );
    let client = ClientBuilder::new(lookup("anthropic").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .build()
        .unwrap();
    let result = client
        .chat(
            "claude",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            None,
        )
        .unwrap();
    server.join().unwrap();
    assert_eq!(result.content, fixture["anthropic_mixed_content"]);
}

#[test]
fn base_query_stays_after_the_joined_chat_path() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        200,
        r#"{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}"#,
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1?api-version=2026-01-01"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    client
        .chat(
            "gpt-5",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            None,
        )
        .unwrap();
    let (headers, _, _) = server.join().unwrap();
    assert!(headers.starts_with(&format!(
        "POST {}?{} HTTP/1.1",
        fixture["openai_query_chat"]["path"].as_str().unwrap(),
        fixture["openai_query_chat"]["query"].as_str().unwrap()
    )));

    let (url, server) = mock_server(
        200,
        r#"{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}"#,
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1/../api/./?api-version=2026-01-01"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    client
        .chat(
            "gpt-5",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            None,
        )
        .unwrap();
    let (headers, _, _) = server.join().unwrap();
    assert!(headers.starts_with(&format!(
        "POST {}?{} HTTP/1.1",
        fixture["openai_dot_path_chat"]["path"].as_str().unwrap(),
        fixture["openai_dot_path_chat"]["query"].as_str().unwrap()
    )));
}

#[test]
fn caller_agent_routes_requests_through_its_proxy() {
    let (proxy_url, proxy) = mock_connect_proxy(r#"{"models":[{"name":"proxied-model"}]}"#);
    let agent = Agent::config_builder()
        .http_status_as_error(false)
        .max_redirects(0)
        .timeout_global(Some(DEFAULT_TIMEOUT))
        .proxy(Some(Proxy::new(&proxy_url).unwrap()))
        .build()
        .into();
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url("http://transport-injection.invalid")
        .agent(agent)
        .build()
        .unwrap();

    let result = client.list_models();
    let (connect, headers) = proxy.join().unwrap();
    let models = result.unwrap_or_else(|error| panic!("{error}; request was: {connect}{headers}"));

    assert_eq!(models[0].id, "proxied-model");
    assert!(connect.starts_with("CONNECT transport-injection.invalid:80 HTTP/1.1"));
    assert!(headers.starts_with("GET /api/tags HTTP/1.1"));
}

#[test]
fn openai_and_anthropic_dialects_emit_their_go_wire_shapes() {
    let (url, server) = mock_server(
        200,
        r#"{"choices":[{"message":{"content":"answer","tool_calls":[{"id":"call-1","type":"function","function":{"name":"lookup","arguments":"{\"q\":\"x\"}"}}]},"finish_reason":"tool_calls"}]}"#,
    );
    let descriptor = lookup("openai").unwrap().clone();
    let client = ClientBuilder::new(descriptor, "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let options = ChatOptions {
        system: "system prompt".into(),
        max_tokens: 32,
        tools: vec![Tool {
            name: "lookup".into(),
            description: "find it".into(),
            parameters: json!({"type":"object"}),
        }],
        response_format: Some(json!({"type":"json_object"})),
        ..Default::default()
    };
    let choice = client
        .chat(
            "",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            Some(&options),
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /v1/chat/completions HTTP/1.1"));
    assert!(
        headers
            .to_ascii_lowercase()
            .contains("authorization: bearer dummy-key")
    );
    let body: Value = serde_json::from_str(&body).unwrap();
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert!(headers.starts_with(&format!(
        "POST {} HTTP/1.1",
        fixture["openai_chat"]["path"].as_str().unwrap()
    )));
    assert_eq!(body["messages"], fixture["openai_chat"]["body"]["messages"]);
    assert_eq!(
        body["max_tokens"],
        fixture["openai_chat"]["body"]["max_tokens"]
    );
    assert_eq!(body["messages"][0]["role"], "system");
    assert_eq!(body["tools"][0]["function"]["name"], "lookup");
    assert_eq!(body["response_format"]["type"], "json_object");
    assert_eq!(choice.content, "answer");
    assert_eq!(choice.tool_calls[0].arguments, json!({"q":"x"}));
    assert_eq!(choice.finish_reason, "tool_calls");

    let (url, server) = mock_server(
        200,
        r#"{"content":[{"type":"text","text":"hello"}],"stop_reason":"end_turn"}"#,
    );
    let client = ClientBuilder::new(lookup("anthropic").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .build()
        .unwrap();
    let choice = client
        .chat(
            "claude",
            &[
                Message {
                    role: "system".into(),
                    content: "rules".into(),
                },
                Message {
                    role: "user".into(),
                    content: "question".into(),
                },
            ],
            None,
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /messages HTTP/1.1"));
    assert!(
        headers
            .to_ascii_lowercase()
            .contains("x-api-key: dummy-key")
    );
    assert!(
        headers
            .to_ascii_lowercase()
            .contains("anthropic-version: 2023-06-01")
    );
    let body: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(
        body["messages"],
        fixture["anthropic_chat"]["body"]["messages"]
    );
    assert_eq!(fixture["anthropic_chat"]["provider_version"], "2023-06-01");
    assert_eq!(body["system"], "rules");
    assert_eq!(body["messages"][0]["role"], "user");
    assert_eq!(body["max_tokens"], 8192);
    assert_eq!(choice.content, "hello");
    assert_eq!(choice.finish_reason, "end_turn");
}

#[test]
fn taxonomy_maps_status_retry_and_exit_codes() {
    let expected = [
        (401, ErrorCode::AuthFailure, ExitCode::NoAuth, false),
        (429, ErrorCode::RateLimited, ExitCode::Conflict, true),
        (404, ErrorCode::ModelNotFound, ExitCode::NotFound, false),
        (500, ErrorCode::ProviderError, ExitCode::Generic, false),
    ];
    for (status, code, exit, retryable) in expected {
        let (url, server) = mock_server(status, " body ");
        let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
            .base_url(url)
            .api_key("dummy-key")
            .build()
            .unwrap();
        let error = client
            .chat(
                "model",
                &[Message {
                    role: "user".into(),
                    content: "x".into(),
                }],
                None,
            )
            .unwrap_err();
        server.join().unwrap();
        assert_eq!(error.code, code);
        assert_eq!(error.exit_code(), exit);
        assert_eq!(error.retryable(), retryable);
        assert_eq!(error.body, "body");
        assert_eq!(error.retry_after_seconds(), Some(17));
    }
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(fixture["rate_limit"]["code"], "rate_limited");
    assert_eq!(fixture["rate_limit"]["retry_after"], "17");
    let (url, server) = mock_server(429, r#"{"error":"busy"}"#);
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let error = client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "x".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    assert_eq!(error.code.as_str(), fixture["rate_limit"]["code"]);
    assert_eq!(error.status_code, fixture["rate_limit"]["status"]);
    assert_eq!(error.body, fixture["rate_limit"]["body"]);
    assert_eq!(error.retry_after, fixture["rate_limit"]["retry_after"]);
    assert_eq!(error.retryable(), fixture["rate_limit"]["retryable"]);
    assert_eq!(
        u8::from(error.exit_code()),
        fixture["rate_limit"]["exit_code"]
    );
    let (url, server) = mock_server(
        401,
        r#"{"error":{"message":"authentication failed","type":"authentication_error"}}"#,
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let error = client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "x".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    assert_eq!(error.code.as_str(), fixture["structured_auth"]["code"]);
    assert_eq!(error.status_code, fixture["structured_auth"]["status"]);
    assert_eq!(error.body, fixture["structured_auth"]["body"]);
    assert_eq!(error.retry_after, fixture["structured_auth"]["retry_after"]);
    assert_eq!(error.retryable(), fixture["structured_auth"]["retryable"]);
    assert_eq!(
        u8::from(error.exit_code()),
        fixture["structured_auth"]["exit_code"]
    );
    let (url, server) = mock_server(400, "context window exceeded");
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .build()
        .unwrap();
    let error = client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "x".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    assert_eq!(error.code, ErrorCode::ContextOverflow);
}

#[test]
fn structured_error_fields_follow_go_json_casefolding() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        401,
        r#"{"ERROR":{"MESSAGE":"authentication failed","TYPE":"authentication_error"}}"#,
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy-key")
        .build()
        .unwrap();
    let error = client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "x".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    let expected = &fixture["structured_auth_casefold"];
    assert_eq!(error.code.as_str(), expected["code"]);
    assert_eq!(error.status_code, expected["status"]);
    assert_eq!(error.body, expected["body"]);
    assert_eq!(error.retry_after, expected["retry_after"]);
    assert_eq!(error.retryable(), expected["retryable"]);
    assert_eq!(u8::from(error.exit_code()), expected["exit_code"]);
}

#[test]
fn malformed_openai_error_envelopes_keep_go_http_classification() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let cases = [
        (
            401,
            r#"{"error":{"message":"authentication failed","type":"authentication_error"},"choices":"malformed"}"#,
            "malformed_error_envelope",
        ),
        (
            429,
            r#"{"error":{"message":"rate limit exceeded","type":"rate_limit_error"},"choices":[{"message":"malformed"}]}"#,
            "malformed_error_choice",
        ),
        (
            401,
            r#"{"choices":[],"error":{"message":"authentication failed","type":"authentication_error"},"CHOICES":"malformed"}"#,
            "malformed_error_choice_alias_collision",
        ),
        (
            401,
            r#"{"error":{"message":"authentication failed","type":"authentication_error"},"choices":[{"message":{"content":"ok","CONTENT":5}}]}"#,
            "malformed_error_nested_alias_collision",
        ),
    ];
    let token = CancellationToken::new();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    for (status, body, fixture_case) in cases {
        for cancellable in [false, true] {
            let (url, server) = mock_server(status, body);
            let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
                .base_url(url)
                .api_key("dummy-key")
                .build()
                .unwrap();
            let messages = [Message {
                role: "user".into(),
                content: "question".into(),
            }];
            let error = if cancellable {
                runtime
                    .block_on(client.chat_cancellable(&token, "model", &messages, None))
                    .unwrap_err()
            } else {
                client.chat("model", &messages, None).unwrap_err()
            };
            server.join().unwrap();
            let expected = &fixture[fixture_case];
            assert_eq!(error.code.as_str(), expected["code"]);
            assert_eq!(error.status_code, expected["status"]);
            assert_eq!(error.body, expected["body"]);
            assert_eq!(error.retry_after, expected["retry_after"]);
            assert_eq!(error.retryable(), expected["retryable"]);
            assert_eq!(u8::from(error.exit_code()), expected["exit_code"]);
        }
    }
}

#[test]
fn streaming_and_embedding_calls_preserve_openai_wire_options() {
    let (url, server) = mock_server(
        200,
        "data: {\"choices\":[{\"delta\":{\"content\":\"piece\"},\"finish_reason\":null}]}\n\ndata: {\"choices\":[{\"delta\":{},\"finish_reason\":\"stop\"}]}\n\ndata: [DONE]\n",
    );
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy")
        .build()
        .unwrap();
    let mut output = String::new();
    let mut finish = String::new();
    client
        .stream_chat(
            "",
            &[Message {
                role: "user".into(),
                content: "hi".into(),
            }],
            None,
            |part| {
                output.push_str(part);
                Ok(())
            },
            |reason| finish = reason.into(),
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    let body: Value = serde_json::from_str(&body).unwrap();
    assert!(headers.starts_with("POST /v1/chat/completions HTTP/1.1"));
    assert_eq!(body["stream"], true);
    assert!(body.get("temperature").is_none());
    assert!(body.get("max_tokens").is_none());
    assert_eq!(output, "piece");
    assert_eq!(finish, "stop");

    let (url, server) = mock_server(200, r#"{"data":[{"embedding":[0.25,0.5]}]}"#);
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy")
        .build()
        .unwrap();
    let embeddings = client.embed("", &["input".into()], Some(2)).unwrap();
    let (_, body, _) = server.join().unwrap();
    let body: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(body["dimensions"], 2);
    assert_eq!(embeddings[0].vector, [0.25, 0.5]);
    assert_eq!(embeddings[0].model, "gpt-5");
}

#[test]
fn embedding_response_fields_match_go_case_insensitive_json() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let cases = [
        (
            r#"{"data":[{"embedding":[0.1]}],"dAtA":[{"embedding":[0.2]}]}"#,
            "data_then_alias",
        ),
        (
            r#"{"dAtA":[{"embedding":[0.3]}],"data":[{"embedding":[0.4]}]}"#,
            "alias_then_data",
        ),
        (
            r#"{"data":[{"embedding":[0.5],"eMbEdDiNg":[0.6]}]}"#,
            "embedding_then_alias",
        ),
        (
            r#"{"data":[{"eMbEdDiNg":[0.7],"embedding":[0.8]}]}"#,
            "alias_then_embedding",
        ),
    ];
    for (response, fixture_case) in cases {
        let (url, server) = mock_server(200, response);
        let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
            .base_url(format!("{url}/v1"))
            .api_key("dummy-key")
            .build()
            .unwrap();
        let embeddings = client.embed("", &["input".into()], None).unwrap();
        server.join().unwrap();
        assert_eq!(embeddings.len(), 1);
        assert_eq!(
            serde_json::to_value(&embeddings[0].vector).unwrap(),
            fixture["casefold_embedding"][fixture_case],
            "Go JSON field matching drift for {fixture_case}"
        );
    }
}

#[test]
fn credentials_fail_closed_and_redirects_are_not_followed() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    assert_eq!(fixture["loopback_query_base_allowed"], true);
    assert!(
        ClientBuilder::new(lookup("openai").unwrap().clone(), "")
            .base_url("http://localhost:11434?api-version=2026-01-01")
            .api_key("dummy-key")
            .build()
            .is_ok()
    );
    let mut descriptor = lookup("openai").unwrap().clone();
    descriptor.base_url = "http://provider.example/v1".into();
    let error = match ClientBuilder::new(descriptor, "env://MISSING_TEST_CREDENTIAL").build() {
        Err(error) => error,
        Ok(_) => panic!("credentialed non-loopback HTTP must be rejected"),
    };
    assert_eq!(error.code, ErrorCode::AuthFailure);
    assert!(error.to_string().contains("requires an HTTPS base URL"));
    assert!(!error.to_string().contains("MISSING_TEST_CREDENTIAL"));

    let name = format!("SYMAIRA_COREKIT_LLM_MISSING_{}", std::process::id());
    assert!(std::env::var_os(&name).is_none());
    let error = match ClientBuilder::new(lookup("openai").unwrap().clone(), format!("env://{name}"))
        .build()
    {
        Err(error) => error,
        Ok(_) => panic!("missing credential should fail"),
    };
    assert_eq!(error.code, ErrorCode::AuthFailure);
    assert!(error.to_string().contains(&format!(
        "environment variable {name} is not set (reference env://{name})"
    )));

    let (url, server) = mock_server(302, "redirect");
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy")
        .build()
        .unwrap();
    let error = client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "x".into(),
            }],
            None,
        )
        .unwrap_err();
    server.join().unwrap();
    assert_eq!(error.status_code, 302);
    assert_eq!(error.code, ErrorCode::ProviderError);
}

#[test]
fn native_ollama_calls_match_go_recordings() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        200,
        "{\"model\":\"llama3.1\",\"response\":\"piece\",\"done\":false}\n{\"model\":\"llama3.1\",\"response\":\"\",\"done\":true}\n",
    );
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let mut chunks = Vec::new();
    client
        .generate(
            "",
            "prompt",
            &GenerateOption {
                system: Some("system".into()),
                format: Some(json!("json")),
                temperature: Some(0.25),
                images: vec!["aW1hZ2U=".into()],
            },
            |chunk| {
                chunks.push(chunk);
                Ok(())
            },
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /api/generate HTTP/1.1"));
    let body: Value = serde_json::from_str(&body).unwrap();
    assert_eq!(body, fixture["native_generate"]["request"]["body"]);
    assert_eq!(
        serde_json::to_value(chunks).unwrap(),
        fixture["native_generate"]["chunks"]
    );

    let (url, server) = mock_server(
        200,
        "{\"model\":\"llama3.1\",\"message\":{\"role\":\"assistant\",\"content\":\"piece\"},\"done\":true}\n",
    );
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let mut chunks = Vec::new();
    client
        .chat_stream(
            "",
            &[Message {
                role: "user".into(),
                content: "question".into(),
            }],
            &NativeChatOption {
                temperature: Some(0.5),
                format: Some("json".into()),
            },
            |chunk| {
                chunks.push(chunk);
                Ok(())
            },
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /api/chat HTTP/1.1"));
    assert_eq!(
        serde_json::from_str::<Value>(&body).unwrap(),
        fixture["native_chat"]["request"]["body"]
    );
    assert_eq!(
        serde_json::to_value(chunks).unwrap(),
        fixture["native_chat"]["chunks"]
    );

    let (url, server) = mock_server(200, r#"{"embeddings":[[0.25,0.5]]}"#);
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let embeddings = client.embed_native("", &["input".into()], 2).unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /api/embed HTTP/1.1"));
    assert_eq!(
        serde_json::from_str::<Value>(&body).unwrap(),
        fixture["native_embed"]["request"]["body"]
    );
    assert_eq!(
        serde_json::to_value(embeddings).unwrap(),
        fixture["native_embed"]["embeddings"]
    );

    let (url, server) = mock_server(
        200,
        r#"{"models":[{"name":"llama3.1","modified_at":"today","size":12}]}"#,
    );
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let models = client.list_ollama_models().unwrap();
    let (headers, _, _) = server.join().unwrap();
    assert!(headers.starts_with("GET /api/tags HTTP/1.1"));
    assert_eq!(
        serde_json::to_value(models).unwrap(),
        fixture["native_models"]["models"]
    );

    let (url, server) = mock_server(
        200,
        r#"{"models":[{"name":"older-model","modified_at":"yesterday","size":99}],"MODELS":[{"NAME":"current-model","MODIFIED_AT":"today","SIZE":12}]}"#,
    );
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let models = client.list_ollama_models().unwrap();
    server.join().unwrap();
    assert_eq!(
        serde_json::to_value(models).unwrap(),
        fixture["native_models_casefold_alias_order"]
    );
}

#[test]
fn openrouter_model_discovery_uses_go_casefold_alias_order() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let (url, server) = mock_server(
        200,
        r#"{"data":[{"id":"older-model"}],"DaTa":[{"ID":"vendor/current-model"}]}"#,
    );
    let client = ClientBuilder::new(lookup("openrouter").unwrap().clone(), "")
        .base_url(format!("{url}/api/v1"))
        .api_key("dummy")
        .build()
        .unwrap();

    let models = client.list_models().unwrap();
    let (headers, _, _) = server.join().unwrap();
    assert!(headers.starts_with("GET /api/v1/models HTTP/1.1"));
    assert_eq!(
        serde_json::to_value(models).unwrap(),
        fixture["casefold_discovery_models"]
    );
}

#[test]
fn native_ollama_generate_accepts_go_scanner_large_chunks() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let response_bytes = fixture["native_generate_large_chunk_response_bytes"]
        .as_u64()
        .expect("pinned Go oracle records large NDJSON response bytes")
        as usize;
    assert_eq!(response_bytes, 2 * 1024 * 1024);

    let response = json!({
        "model":"llama3.1",
        "response":"x".repeat(response_bytes),
        "done":true
    })
    .to_string()
        + "\n";
    let (url, server) = mock_server(200, response);
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let mut observed_bytes = None;
    client
        .generate("", "prompt", &GenerateOption::default(), |chunk| {
            observed_bytes = Some(chunk.response.len());
            Ok(())
        })
        .unwrap();
    server.join().unwrap();
    assert_eq!(observed_bytes, Some(response_bytes));
}

#[test]
fn native_ollama_generate_scanner_errors_match_go_before_and_after_data() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let oversized_line = json!({
        "model":"llama3.1",
        "response":"x".repeat(4 * 1024 * 1024),
        "done":true
    })
    .to_string()
        + "\n";

    for (prefix, expected_case, expected_callbacks) in [
        ("", "before_data", 0),
        (
            "{\"model\":\"llama3.1\",\"response\":\"first\",\"done\":false}\n",
            "after_data",
            1,
        ),
    ] {
        let (url, server) = mock_server(200, format!("{prefix}{oversized_line}"));
        let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
            .base_url(url)
            .build()
            .unwrap();
        let mut callbacks = 0;
        let error = client
            .generate("", "prompt", &GenerateOption::default(), |_| {
                callbacks += 1;
                Ok(())
            })
            .unwrap_err();
        server.join().unwrap();

        let expected = &fixture["native_generate_scanner_errors"][expected_case];
        assert_eq!(error.code.as_str(), expected["code"]);
        assert_eq!(error.to_string(), expected["error"]);
        assert_eq!(callbacks, expected_callbacks);
    }
}

#[test]
fn anthropic_stream_and_openrouter_model_discovery_are_normalized() {
    let (url, server) = mock_server(
        200,
        "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"piece\"}}\n\ndata: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"}}\n\n",
    );
    let client = ClientBuilder::new(lookup("anthropic").unwrap().clone(), "")
        .base_url(url)
        .api_key("dummy")
        .build()
        .unwrap();
    let mut output = String::new();
    let mut finish = String::new();
    client
        .stream_chat(
            "claude",
            &[Message {
                role: "user".into(),
                content: "hi".into(),
            }],
            None,
            |part| {
                output.push_str(part);
                Ok(())
            },
            |reason| finish = reason.into(),
        )
        .unwrap();
    let (headers, body, _) = server.join().unwrap();
    assert!(headers.starts_with("POST /messages HTTP/1.1"));
    assert_eq!(
        serde_json::from_str::<Value>(&body).unwrap()["stream"],
        true
    );
    assert_eq!(output, "piece");
    assert_eq!(finish, "end_turn");

    let (url, server) = mock_server(200, r#"{"data":[{"id":"model-a"},{"id":"model-b"}]}"#);
    let client = ClientBuilder::new(lookup("openrouter").unwrap().clone(), "")
        .base_url(format!("{url}/api/v1"))
        .api_key("dummy")
        .build()
        .unwrap();
    let models = client.list_models().unwrap();
    let (headers, _, _) = server.join().unwrap();
    assert!(headers.starts_with("GET /api/v1/models HTTP/1.1"));
    assert_eq!(
        models
            .iter()
            .map(|model| model.id.as_str())
            .collect::<Vec<_>>(),
        ["model-a", "model-b"]
    );
}
