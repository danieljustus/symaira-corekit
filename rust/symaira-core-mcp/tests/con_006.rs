use std::io::{self, Cursor, Write};
use std::sync::{Arc, Mutex};

use serde_json::Value;
use symaira_core_mcp::{Server, Tool, ToolAnnotations};

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
fn con_006_tool_annotations_match_fixture_wire_names() {
    let fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/mcp_tool_annotations.json"
    ))
    .unwrap();
    let server = Server::new("test", "1.0");
    server
        .register_tool(
            Tool::new("annotated", "annotated").annotations(ToolAnnotations {
                title: String::new(),
                read_only_hint: true,
                idempotent_hint: true,
                open_world_hint: true,
                destructive_hint: true,
            }),
        )
        .unwrap();
    let input = b"{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/list\"}\n";
    let output = Arc::new(Mutex::new(Vec::new()));
    server
        .serve_io(Cursor::new(input.to_vec()), Capture(Arc::clone(&output)))
        .unwrap();
    let listed: Value = serde_json::from_slice(&output.lock().unwrap()).unwrap();
    let annotations = &listed["result"]["tools"][0]["annotations"];

    let hints = fixture["hints"].as_array().unwrap();
    let expected: std::collections::BTreeSet<_> = hints
        .iter()
        .map(|hint| {
            assert_eq!(hint["type"], "boolean");
            hint["wire_name"].as_str().unwrap()
        })
        .collect();
    let got: std::collections::BTreeSet<_> = annotations
        .as_object()
        .unwrap()
        .keys()
        .map(String::as_str)
        .collect();
    assert_eq!(got, expected);
    assert_eq!(annotations["readOnlyHint"], true);
    assert_eq!(
        hints
            .iter()
            .filter(|hint| hint["must_be_declared_explicitly"] == true)
            .count(),
        1
    );
    assert!(
        fixture["explicit_declaration_rule"]
            .as_str()
            .unwrap()
            .contains("readOnlyHint")
    );
}
