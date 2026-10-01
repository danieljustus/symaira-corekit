use serde_json::{Value, json};
use std::io::{Read, Write};
use std::net::TcpListener;
use std::thread;
use symaira_core_exit::ExitCode;
use symaira_core_llm::{AuthScheme, ClientBuilder, ErrorCode, Message, lookup, providers};

fn exit_name(code: ExitCode) -> &'static str {
    match code {
        ExitCode::NoAuth => "ExitNoAuth",
        ExitCode::Conflict => "ExitConflict",
        ExitCode::Data => "ExitData",
        ExitCode::NotFound => "ExitNotFound",
        ExitCode::Generic => "ExitGeneric",
        _ => panic!("unexpected exit code {code:?}"),
    }
}

#[test]
fn con_008_provider_registry_and_error_taxonomy_match_fixtures() {
    let providers_fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/llm_providers.json"
    ))
    .unwrap();
    let errors_fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/llm_errors.json"
    ))
    .unwrap();
    let actual = providers();
    assert_eq!(providers_fixture["schema_version"], 1);
    assert_eq!(
        actual.len(),
        providers_fixture["providers"].as_array().unwrap().len()
    );

    for provider in actual {
        let expected = providers_fixture["providers"]
            .as_array()
            .unwrap()
            .iter()
            .find(|entry| entry["id"] == provider.id)
            .unwrap_or_else(|| panic!("provider {} missing from fixture", provider.id));
        let mut auth = match provider.auth_scheme {
            symaira_core_llm::AuthScheme::Bearer => json!({"scheme":"bearer"}),
            symaira_core_llm::AuthScheme::Header => {
                json!({"scheme":"header", "header":provider.auth_header})
            }
            symaira_core_llm::AuthScheme::None => json!({"scheme":"none"}),
        };
        if provider.id == "custom" {
            // Descriptor.auth_scheme is public and is exercised below through a real request.
            auth["configurable_scheme"] = json!(true);
        }
        let dialect = match provider.dialect {
            symaira_core_llm::WireDialect::Openai => "openai",
            symaira_core_llm::WireDialect::Anthropic => "anthropic",
        };
        let mut models = serde_json::to_value(&provider.models).unwrap();
        // The Rust registry encodes no default model as ""; the neutral JSON
        // contract represents the same absence as null.
        if models["default"] == "" {
            models["default"] = Value::Null;
        }
        let mut actual = json!({
            "id": provider.id,
            "display_name": provider.display_name,
            "base_url": if provider.base_url.is_empty() { Value::Null } else { json!(provider.base_url) },
            "auth": auth,
            "dialect": dialect,
            "capabilities": provider.capabilities,
            "models": models,
            "credential_ref_env_default": if provider.credential_env_default.is_empty() { Value::Null } else { json!(provider.credential_env_default) },
        });
        if provider.base_url_overridable {
            actual["base_url_overridable"] = json!(true);
        }
        if provider.base_url_required_override {
            actual["base_url_required_override"] = json!(true);
        }
        if !provider.extra_headers.is_empty() {
            actual["extra_headers"] = json!(provider.extra_headers);
        }
        if provider.dialect_configurable {
            actual["dialect_configurable"] = json!(true);
        }
        // The Rust source is a generated copy with idiomatic field names; compare its
        // runtime descriptors after mapping them to the language-neutral wire schema.
        assert_eq!(actual, *expected, "provider {} drifted", provider.id);
    }

    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut request = Vec::new();
        let mut chunk = [0; 2048];
        let header_end = loop {
            let size = stream.read(&mut chunk).unwrap();
            request.extend_from_slice(&chunk[..size]);
            if let Some(end) = request.windows(4).position(|bytes| bytes == b"\r\n\r\n") {
                break end + 4;
            }
        };
        let header = String::from_utf8_lossy(&request[..header_end]).into_owned();
        let content_length = header
            .lines()
            .find_map(|line| {
                let (name, value) = line.split_once(':')?;
                name.eq_ignore_ascii_case("content-length")
                    .then(|| value.trim().parse::<usize>().ok())
                    .flatten()
            })
            .unwrap_or(0);
        while request.len() < header_end + content_length {
            let size = stream.read(&mut chunk).unwrap();
            request.extend_from_slice(&chunk[..size]);
        }
        let response = r#"{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}"#;
        write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{response}", response.len()).unwrap();
        header
    });
    let mut custom = lookup("custom").unwrap().clone();
    custom.auth_scheme = AuthScheme::Header;
    custom.auth_header = "X-Custom-Key".into();
    let client = ClientBuilder::new(custom, "")
        .base_url(url)
        .api_key("test-key")
        .build()
        .unwrap();
    client
        .chat(
            "model",
            &[Message {
                role: "user".into(),
                content: "hello".into(),
            }],
            None,
        )
        .unwrap();
    let request = server.join().unwrap().to_ascii_lowercase();
    assert!(request.contains("x-custom-key: test-key"));

    let expected_errors = errors_fixture["errors"].as_array().unwrap();
    assert_eq!(errors_fixture["schema_version"], 1);
    let actual_errors = [
        (ErrorCode::AuthFailure, "auth_failure"),
        (ErrorCode::RateLimited, "rate_limited"),
        (ErrorCode::ContextOverflow, "context_overflow"),
        (ErrorCode::ModelNotFound, "model_not_found"),
        (ErrorCode::TransportError, "transport_error"),
        (ErrorCode::ProviderError, "provider_error"),
    ];
    assert_eq!(actual_errors.len(), expected_errors.len());
    for (code, name) in actual_errors {
        let expected = expected_errors
            .iter()
            .find(|entry| entry["code"] == name)
            .unwrap_or_else(|| panic!("error {name} missing from fixture"));
        assert_eq!(code.as_str(), name);
        assert_eq!(code.retryable(), expected["retryable"]);
        assert_eq!(exit_name(code.exit_code()), expected["exit_code"]);
    }
}
