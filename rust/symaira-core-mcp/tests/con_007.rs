use std::io::{self, Cursor, Write};
use std::sync::{Arc, Mutex};

use serde_json::{Map, Value, json};
use symaira_core_mcp::{Server, Tool, ToolError};

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

fn call(with_metadata: bool) -> Value {
    let server = Server::new("test", "1.0");
    server
        .register_tool(Tool::new("fail", "fail").handler(move |_, _| {
            let error = if with_metadata {
                ToolError::new("peer denied")
                    .code("peer_denied")
                    .retryable(false)
                    .requires_confirmation(false)
                    .resume_hint("pick an allowed path")
                    .hint("check the path")
                    .details(Map::from_iter([("rule".into(), json!("blocked"))]))
            } else {
                ToolError::new("plain failure")
            };
            Err(Box::new(error))
        }))
        .unwrap();
    let input = b"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"fail\",\"arguments\":{}}}\n";
    let output = Arc::new(Mutex::new(Vec::new()));
    server
        .serve_io(Cursor::new(input.to_vec()), Capture(Arc::clone(&output)))
        .unwrap();
    serde_json::from_slice(&output.lock().unwrap()).unwrap()
}

#[test]
fn con_007_tool_errors_are_mcp_results_with_fixture_metadata() {
    let fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/mcp_tool_errors.json"
    ))
    .unwrap();
    let response = call(true);
    let result = &response["result"];
    assert_eq!(result["isError"], true);
    assert!(response.get("error").is_none());
    let meta_key = fixture["meta_key"].as_str().unwrap();
    let metadata = &result["_meta"][meta_key];
    let expected: std::collections::BTreeSet<_> = fixture["fields"]
        .as_array()
        .unwrap()
        .iter()
        .map(|field| field["wire_name"].as_str().unwrap())
        .collect();
    let got: std::collections::BTreeSet<_> = metadata
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(got, expected);
    assert_eq!(metadata["message"], result["content"][0]["text"]);
    assert_eq!(metadata["retryable"], false);
    assert_eq!(metadata["requires_confirmation"], false);
    assert_eq!(fixture["key_case"], "snake_case");

    let empty = call(false);
    assert_eq!(empty["result"]["isError"], true);
    if fixture["omit_when_empty"].as_bool().unwrap() {
        assert!(empty["result"].get("_meta").is_none());
    } else {
        assert!(empty["result"].get("_meta").is_some());
    }
}
