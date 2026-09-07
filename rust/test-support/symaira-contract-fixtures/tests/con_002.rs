use std::fs;
use std::path::PathBuf;

#[test]
fn con_002_config_paths_fixture_is_byte_stable() {
    let expected =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../contracts/config_paths.json");
    assert_eq!(
        symaira_contract_fixtures::CONFIG_PATHS,
        fs::read(expected)
            .expect("source fixture exists")
            .as_slice()
    );
    let fixture = symaira_contract_fixtures::json(symaira_contract_fixtures::CONFIG_PATHS);
    assert_eq!(fixture["config_file_format"], "toml");
    assert!(
        fixture["config_path_pattern"]
            .as_str()
            .unwrap()
            .contains("XDG_CONFIG_HOME")
    );
}
