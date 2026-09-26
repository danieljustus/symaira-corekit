#![deny(unsafe_code)]

use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;
use symaira_core_exit::ExitCode;
use symaira_core_llm::{
    ChatOptions, ClientBuilder, ErrorCode, GenerateOption, Message, NativeChatOption, Tool, lookup,
    providers,
};

fn mock_server(
    status: u16,
    response: &'static str,
) -> (String, thread::JoinHandle<(String, String, String)>) {
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
fn credentials_fail_closed_and_redirects_are_not_followed() {
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
