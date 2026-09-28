use serde::Deserialize;
use serde_json::Value;
use std::path::PathBuf;
use symaira_core_update::cosign_contract::{Input, replay};

#[derive(Deserialize)]
struct Fixture {
    goos: String,
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    input: Value,
    result: Value,
}

#[test]
fn cosign_contract_observations_match_go_api() {
    let default_fixture = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../testdata/rust-port/fixtures/update/cosign.json");
    let fixture_path = std::env::var_os("COSIGN_CONTRACT_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_str(
        &std::fs::read_to_string(fixture_path).expect("read generated cosign fixture"),
    )
    .expect("valid generated cosign fixture");
    assert!(matches!(
        fixture.goos.as_str(),
        "darwin" | "linux" | "windows"
    ));
    assert_eq!(fixture.cases.len(), 13);
    for case in fixture.cases {
        let input = Input {
            artifact: string(&case.input, "artifact"),
            version: string(&case.input, "version"),
            binary: string(&case.input, "binary"),
            repo: string(&case.input, "repo"),
            identity: string(&case.input, "identity"),
            identity_regexp: string(&case.input, "identity_regexp"),
        };
        let output = replay(&case.id, &input);
        let actual = match case.id.as_str() {
            "fetch-signature"
            | "fetch-certificate"
            | "fetch-http-404"
            | "fetch-too-large"
            | "fetch-empty-version" => {
                let mut value = serde_json::json!({"body":output.body,"request":output.request});
                add_errors(&mut value, &output);
                value
            }
            "fetch-http-url" => {
                let mut value = serde_json::json!({});
                add_errors(&mut value, &output);
                value
            }
            id if id.starts_with("identity-") => {
                serde_json::json!({"pattern":output.pattern,"matches":output.matches})
            }
            _ => serde_json::json!({
                "argv":output.argv,"content":output.content,"signature":output.signature,
                "certificate":output.certificate,"error_code":output.error_code,
                "error_message":output.error_message,
            }),
        };
        assert_eq!(actual, case.result, "case {}", case.id);
    }
}

fn string(value: &Value, key: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_owned()
}

fn add_errors(value: &mut Value, output: &symaira_core_update::cosign_contract::Output) {
    if !output.error_code.is_empty() {
        value["error_code"] = Value::String(output.error_code.clone());
        value["error_message"] = Value::String(output.error_message.clone());
    }
}
