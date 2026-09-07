use std::collections::HashMap;
use std::io::{self, Cursor, Write};
use std::sync::{Arc, Mutex};

use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::Value;
use symaira_core_mcp::{Server, Tool, ToolOutput};

#[derive(Clone)]
struct Capture(Arc<Mutex<Vec<u8>>>);

impl Write for Capture {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(bytes);
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn run(server: &Server, input: Vec<u8>) -> Vec<u8> {
    let output = Arc::new(Mutex::new(Vec::new()));
    server
        .serve_io(Cursor::new(input), Capture(Arc::clone(&output)))
        .unwrap();
    output.lock().unwrap().clone()
}

fn line(body: &str) -> Vec<u8> {
    format!("{body}\n").into_bytes()
}

fn framed(body: &str) -> Vec<u8> {
    format!("Content-Length: {}\r\n\r\n{body}", body.len()).into_bytes()
}

fn framed_body(frame: &[u8]) -> &[u8] {
    let separator = frame
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .unwrap();
    &frame[separator + 4..]
}

#[test]
fn raw_frames_support_line_and_content_length_transports() {
    for input in [
        line(r#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#),
        framed(r#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#),
    ] {
        let output = String::from_utf8(run(&Server::new("test", "1.0"), input)).unwrap();
        assert!(output.contains(r#""jsonrpc":"2.0""#));
        assert!(output.contains(r#""result":{}"#));
    }
}

#[test]
fn framed_transport_accepts_exact_header_line_boundary() {
    let body = r#"{"jsonrpc":"2.0","id":1,"method":"ping"}"#;
    let mut input = format!("Content-Length: {}\r\n", body.len());
    for _ in 1..symaira_core_mcp::MAX_HEADER_LINES {
        input.push_str("X-Ignored: value\r\n");
    }
    input.push_str("\r\n");
    input.push_str(body);

    let output = String::from_utf8(run(&Server::new("test", "1.0"), input.into_bytes())).unwrap();
    assert!(output.contains(r#""result":{}"#));
}

#[test]
fn raw_frames_preserve_notifications_and_large_ids() {
    let server = Server::new("test", "1.0");
    let notification = line(r#"{"jsonrpc":"2.0","method":"notifications/initialized"}"#);
    assert!(run(&server, notification).is_empty());

    let output = String::from_utf8(run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":9007199254740993,"method":"ping"}"#),
    ))
    .unwrap();
    assert!(output.contains("9007199254740993"));
}

#[test]
fn raw_frames_dispatch_typed_tool_and_reject_unknown_fields() {
    #[derive(Deserialize, JsonSchema)]
    struct Input {
        query: String,
    }

    let server = Server::new("test", "1.0");
    server
        .register_typed::<Input, _>("search", "search", |_, input| {
            Ok(ToolOutput::from(input.query))
        })
        .unwrap();

    let success = run(
        &server,
        line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"ok"}}}"#,
        ),
    );
    assert!(String::from_utf8(success).unwrap().contains("ok"));

    let rejected = run(
        &server,
        line(
            r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search","arguments":{"query":"ok","extra":true}}}"#,
        ),
    );
    let response: Value = serde_json::from_slice(&rejected).unwrap();
    assert_eq!(response["result"]["isError"], Value::Bool(true));
}

#[test]
fn raw_frames_return_tool_results_without_stdout_side_channels() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("echo", "echo").handler(|_, _| Ok(ToolOutput::from("ok"))))
        .unwrap();
    let output = run(
        &server,
        line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo","arguments":{}}}"#,
        ),
    );
    assert_eq!(output.iter().filter(|byte| **byte == b'\n').count(), 1);
    assert!(
        String::from_utf8(output)
            .unwrap()
            .contains(r#""isError":false"#)
    );
}

#[test]
fn registration_boundaries_return_results_without_panicking() {
    let server = Server::new("test", "1.0");
    assert!(server.register_optional_tool(None).is_err());
    assert!(server.register_tool(Tool::new("x", "x")).is_ok());
    assert!(server.register_tool(Tool::new("x", "duplicate")).is_err());
    assert!(server.register_tool(Tool::new("", "empty")).is_err());
}

#[test]
fn annotations_preserve_all_hints_and_structured_unknown_fields() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("annotated", "all hints").annotations(
            symaira_core_mcp::ToolAnnotations {
                title: "Annotated".into(),
                read_only_hint: true,
                idempotent_hint: true,
                open_world_hint: true,
                destructive_hint: true,
            },
        ))
        .unwrap();
    server
        .register_tool(Tool::new("plain", "no hints"))
        .unwrap();
    let listed: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
    ))
    .unwrap();
    assert_eq!(
        listed["result"]["tools"][0]["annotations"]["openWorldHint"],
        true
    );
    assert_eq!(
        listed["result"]["tools"][0]["annotations"]["destructiveHint"],
        true
    );
    assert!(listed["result"]["tools"][1].get("annotations").is_none());

    let structured = Tool::new("structured", "structured").handler(|_, _| {
        Ok(ToolOutput::Result(symaira_core_mcp::ToolResult {
            content: vec![],
            structured_content: Some(serde_json::json!({
                "annotations": {"futureHint": true, "unknown": {"keep": 1}}
            })),
            meta: None,
        }))
    });
    server.register_tool(structured).unwrap();
    let response: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"structured","arguments":{}}}"#),
    ))
    .unwrap();
    assert_eq!(
        response["result"]["structuredContent"]["annotations"]["unknown"]["keep"],
        1
    );
}

#[test]
fn bool_result_and_framed_tool_call_are_wire_values() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(
            Tool::new("bool", "bool")
                .handler(|_, _| Ok(ToolOutput::from(serde_json::Value::Bool(true)))),
        )
        .unwrap();
    let body =
        r#"{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"bool","arguments":{}}}"#;
    let raw = run(&server, framed(body));
    let response: Value = serde_json::from_slice(framed_body(&raw)).unwrap();
    assert_eq!(response["result"]["content"][0]["text"], "true");
}

#[test]
fn ids_preserve_fractional_and_beyond_u64_number_bytes() {
    for id in [
        "184467440737095516160000000000000000001",
        "0.123456789012345678901234567890",
    ] {
        let server = Server::new("test", "1.0");
        let body = format!(r#"{{"jsonrpc":"2.0","id":{id},"method":"ping"}}"#);
        let output = run(&server, line(&body));
        assert!(
            String::from_utf8(output).unwrap().contains(id),
            "id {id} was normalized"
        );
    }
}

#[test]
fn invalid_present_name_type_is_invalid_params_and_meta_reaches_handler() {
    let server = Server::new("test", "1.0");
    for name in ["1", "true", "null", "{}", "[]"] {
        let request = format!(
            r#"{{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{{"name":{name}}}}}"#
        );
        let invalid: Value = serde_json::from_slice(&run(&server, line(&request))).unwrap();
        assert_eq!(invalid["error"]["code"], -32602, "name={name}");
    }

    server
        .register_tool(Tool::new("meta", "meta").handler(|token, _| {
            let meta = token.request_meta().unwrap();
            Ok(ToolOutput::from(meta["trace"]["id"].clone()))
        }))
        .unwrap();
    let response: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"meta","_meta":{"trace":{"id":"abc"}},"arguments":{}}}"#),
    ))
    .unwrap();
    assert_eq!(response["result"]["content"][0]["text"], "abc");
}

#[derive(Debug)]
struct WrappedToolError {
    inner: symaira_core_mcp::ToolError,
}

impl std::fmt::Display for WrappedToolError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "wrapped: {}", self.inner)
    }
}

impl std::error::Error for WrappedToolError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.inner)
    }
}

#[test]
fn boxed_errors_traverse_sources_for_tool_metadata() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("wrapped", "wrapped").handler(|_, _| {
            Err(Box::new(WrappedToolError {
                inner: symaira_core_mcp::ToolError::new("denied").code("policy"),
            }) as Box<dyn std::error::Error + Send + Sync>)
        }))
        .unwrap();
    let response: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"wrapped","arguments":{}}}"#),
    ))
    .unwrap();
    assert_eq!(
        response["result"]["_meta"][symaira_core_mcp::TOOL_ERROR_META_KEY]["code"],
        "policy"
    );
    assert_eq!(
        response["result"]["_meta"][symaira_core_mcp::TOOL_ERROR_META_KEY]["message"],
        "wrapped: denied"
    );
}

#[test]
fn raw_null_arguments_follow_go_zero_value_behavior_on_public_tool_path() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("echo", "echo").handler(|_, input| {
            let message = match input {
                Value::Null => String::new(),
                Value::Object(fields) => fields
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                _ => unreachable!("raw fixture only accepts object or null"),
            };
            Ok(ToolOutput::from(message))
        }))
        .unwrap();
    let response: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo","arguments":null}}"#),
    ))
    .unwrap();
    assert_eq!(response["result"]["isError"], false);
    assert_eq!(response["result"]["content"][0]["text"], "");
}

#[test]
fn typed_missing_fields_use_go_zero_values_and_map_roots_are_rejected() {
    #[derive(Deserialize, JsonSchema)]
    struct Input {
        query: String,
        limit: i64,
        exact: bool,
        tags: Vec<String>,
    }

    let server = Server::new("test", "1.0");
    server
        .register_typed::<Input, _>("typed", "typed", |_, input| {
            Ok(ToolOutput::from(format!(
                "{}:{}:{}:{}",
                input.query,
                input.limit,
                input.exact,
                input.tags.len()
            )))
        })
        .unwrap();
    let response: Value = serde_json::from_slice(&run(
        &server,
        line(r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"typed","arguments":{}}}"#),
    ))
    .unwrap();
    assert_eq!(response["result"]["content"][0]["text"], ":0:false:0");

    assert!(
        server
            .register_typed::<HashMap<String, String>, _>("map", "map", |_, _| {
                Ok(ToolOutput::from("unreachable"))
            })
            .is_err()
    );
    assert!(
        server
            .register_typed::<Vec<String>, _>("array", "array", |_, _| {
                Ok(ToolOutput::from("unreachable"))
            })
            .is_err()
    );
}

#[test]
fn go_json_wire_encoding_escapes_html_and_line_separators() {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("special", "special").handler(|_, _| {
            Ok(ToolOutput::from(serde_json::json!({
                "text": "<>&\u{2028}\u{2029}"
            })))
        }))
        .unwrap();
    let raw = run(
        &server,
        line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"special","arguments":{}}}"#,
        ),
    );
    let wire = String::from_utf8(raw).unwrap();
    assert!(wire.contains(r#"\u003c"#));
    assert!(wire.contains(r#"\u003e"#));
    assert!(wire.contains(r#"\u0026"#));
    assert!(wire.contains(r#"\u2028"#));
    assert!(wire.contains(r#"\u2029"#));
}
