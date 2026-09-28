use std::io::{self, Cursor, Write};
use std::sync::{Arc, Mutex};

use serde_json::{Value, json};
use symaira_core_mcp::{Server, Tool, ToolOutput, ToolResult};

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

#[test]
fn con_003_mcp_json_encoding_uses_fixture_keys_and_framing() {
    let fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/json_encoding.json"
    ))
    .unwrap();
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("echo", "echo").handler(|_, _| {
            Ok(ToolOutput::Result(ToolResult {
                content: vec![],
                structured_content: Some(json!({"item_name": "ok"})),
                meta: None,
            }))
        }))
        .unwrap();

    let body =
        r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"echo","arguments":{}}}"#;
    let input = format!("Content-Length: {}\r\n\r\n{body}", body.len());
    let output = Arc::new(Mutex::new(Vec::new()));
    server
        .serve_io(
            Cursor::new(input.into_bytes()),
            Capture(Arc::clone(&output)),
        )
        .unwrap();
    let output = output.lock().unwrap();

    let header_end = output
        .windows(4)
        .position(|bytes| bytes == b"\r\n\r\n")
        .unwrap();
    let header = std::str::from_utf8(&output[..header_end]).unwrap();
    let response_body = &output[header_end + 4..];
    assert!(header.starts_with("Content-Length: "));
    assert_eq!(
        header["Content-Length: ".len()..].parse::<usize>().unwrap(),
        response_body.len()
    );
    assert_eq!(
        fixture["transport_framing"],
        "Content-Length header followed by CRLFCRLF and the JSON-RPC body, per the MCP stdio transport spec."
    );
    let response: Value = serde_json::from_slice(response_body).unwrap();
    assert_eq!(response["jsonrpc"], "2.0");
    assert!(response.get("jsonRpc").is_none());
    let content_key = match fixture["protocol_envelope_key_case"].as_str().unwrap() {
        "camelCase" => "structuredContent",
        "snake_case" => "structured_content",
        other => panic!("unsupported fixture envelope key case {other}"),
    };
    let payload_key = match fixture["application_json_key_case"].as_str().unwrap() {
        "snake_case" => "item_name",
        "camelCase" => "itemName",
        other => panic!("unsupported fixture application key case {other}"),
    };
    assert_eq!(response["result"][content_key][payload_key], "ok");
    assert!(response["result"].get("structured_content").is_none());
    assert!(response["result"][content_key].get("itemName").is_none());
    assert_eq!(fixture["stdout_pollution"], "forbidden");
}
