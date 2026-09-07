use std::fs;
use std::path::PathBuf;

#[test]
fn con_001_exit_fixture_is_valid_and_byte_stable() {
    let expected =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../contracts/exit_codes.json");
    assert_eq!(
        symaira_contract_fixtures::EXIT_CODES,
        fs::read(expected)
            .expect("source fixture exists")
            .as_slice()
    );
    let rows: Vec<serde_json::Value> =
        serde_json::from_slice(symaira_contract_fixtures::EXIT_CODES).unwrap();
    assert_eq!(rows.len(), 11);
    assert_eq!(rows[0]["code"], 0);
    assert_eq!(rows[10]["name"], "ExitInterrupted");
}
