use symaira_core_version::new;

fn fixture(id: &str) -> serde_json::Value {
    symaira_contract_fixtures::json(symaira_contract_fixtures::foundation(id))
}

#[test]
fn ver_001_json_field_names_order_and_values_are_exact() {
    let expected_fixture = fixture("VER-001");
    let expected = expected_fixture["json"].as_str().unwrap().as_bytes();
    assert_eq!(new("symx", "v1.2.3", 7).json().unwrap(), expected);
    assert_eq!(
        new("<&>", "v<1>&", 7).json().unwrap(),
        expected_fixture["html_json"].as_str().unwrap().as_bytes()
    );
}

#[test]
fn ver_002_text_and_write_match_go() {
    let info = new("symx", "v1.2.3", 7);
    let expected = fixture("VER-002");
    assert_eq!(info.to_string(), expected["text"].as_str().unwrap());
    let mut output = Vec::new();
    info.write(&mut output).unwrap();
    assert_eq!(
        String::from_utf8(output).unwrap(),
        expected["write"].as_str().unwrap()
    );
}
