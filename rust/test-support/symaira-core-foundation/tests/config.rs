use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::sync::Arc;
#[cfg(windows)]
use symaira_core_config::default_path_for_roots;
use symaira_core_config::{
    ConfigSchema, Duration, Loader, Options, apply_env_overrides_from, default_path, duration,
    merge_file,
};

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Config {
    server: Server,
    debug: bool,
    name: String,
    timeout: i64,
    rate: f64,
    #[serde(with = "duration")]
    ttl: Duration,
    tags: Vec<String>,
    allowed: std::collections::BTreeMap<String, i64>,
}
impl ConfigSchema for Config {
    fn map_fields() -> &'static [&'static str] {
        &["allowed"]
    }
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct Server {
    port: i64,
    host: String,
    enabled: Option<bool>,
}
#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
struct TypedConfig {
    optional: Option<String>,
    maximum: u64,
}
impl ConfigSchema for TypedConfig {
    fn map_fields() -> &'static [&'static str] {
        &[]
    }
    fn string_fields() -> &'static [&'static str] {
        &["optional"]
    }
    fn unsigned_fields() -> &'static [&'static str] {
        &["maximum"]
    }
}
fn defaults() -> Config {
    Config {
        server: Server {
            port: 8080,
            host: "localhost".into(),
            enabled: None,
        },
        debug: false,
        name: "default-app".into(),
        timeout: 30,
        rate: 1.5,
        ttl: Duration::from_nanos(900_000_000_000),
        tags: vec!["default".into()],
        allowed: Default::default(),
    }
}
fn nonempty_map_defaults() -> Config {
    let mut config = defaults();
    config.allowed.insert("existing".into(), 1);
    config
}
fn fixture(id: &str) -> serde_json::Value {
    symaira_contract_fixtures::json(symaira_contract_fixtures::foundation(id))
}
fn tempfile_dir() -> PathBuf {
    let path = std::env::temp_dir().join(format!("symaira-core-foundation-{}", std::process::id()));
    std::fs::create_dir_all(&path).unwrap();
    path
}

#[test]
fn cfg_001_default_path_uses_xdg_shape_or_home_fallback() {
    let expected = fixture("CFG-001");
    let path = default_path("symx");
    assert!(path.ends_with(PathBuf::from(".config/symx/config.toml")));
    assert!(path.is_absolute() || path.starts_with(".config"));
    assert!(
        expected["xdg"]
            .as_str()
            .unwrap()
            .ends_with("symx/config.toml")
    );
}

#[test]
fn cfg_002_defaults_and_missing_files_are_preserved() {
    let expected = fixture("CFG-002");
    let mut config = defaults();
    merge_file(
        &mut config,
        std::path::Path::new("/definitely/missing/config.toml"),
    )
    .unwrap();
    let expected_defaults = &expected["defaults"];
    assert_eq!(
        config.server.port,
        expected_defaults["server"]["port"].as_i64().unwrap()
    );
    assert_eq!(
        config.server.host,
        expected_defaults["server"]["host"].as_str().unwrap()
    );
    assert_eq!(config.name, expected_defaults["name"].as_str().unwrap());
    assert_eq!(
        config.timeout,
        expected_defaults["timeout"].as_i64().unwrap()
    );
    assert_eq!(config.rate, expected_defaults["rate"].as_f64().unwrap());
    assert_eq!(config.tags, ["default"]);
    assert!(config.allowed.is_empty());
    assert!(expected["missing_file_error"].as_bool().unwrap());
}

#[test]
fn cfg_003_precedence_is_defaults_global_project_then_env() {
    let root = tempfile_dir();
    let global = root.join("global.toml");
    let project = root.join("project.toml");
    std::fs::write(
        &global,
        "name = \"global\"\ntimeout = 40\n[server]\nport = 9000\n",
    )
    .unwrap();
    std::fs::write(
        &project,
        "name = \"project\"\n[server]\nhost = \"remote\"\n",
    )
    .unwrap();
    let mut config = defaults();
    merge_file(&mut config, &global).unwrap();
    merge_file(&mut config, &project).unwrap();
    apply_env_overrides_from(&mut config, "APP", [("APP_NAME", "environment")]).unwrap();
    let expected = fixture("CFG-003");
    assert_eq!(config.name, expected["name"].as_str().unwrap());
    assert_eq!(config.timeout, expected["timeout"].as_i64().unwrap());
    assert_eq!(config.server.port, expected["port"].as_i64().unwrap());
    assert_eq!(config.server.host, expected["host"].as_str().unwrap());
}

#[test]
fn cfg_004_types_bool_duration_and_slices_match_go_fixture() {
    let expected = fixture("CFG-004");
    for value in [
        "t", "T", "true", "TRUE", "True", "1", "f", "F", "false", "FALSE", "False", "0",
    ] {
        let mut config = defaults();
        apply_env_overrides_from(&mut config, "APP", [("APP_DEBUG", value)]).unwrap();
        assert_eq!(config.debug, expected["bools"][value].as_bool().unwrap());
    }
    assert_eq!(
        duration::format_duration(duration::parse_duration("-1.5s").unwrap()),
        expected["negative_duration"].as_str().unwrap()
    );
    assert!(duration::parse_duration("999999999999999999999h").is_err());
    assert!(expected["overflow_error"].as_bool().unwrap());
    for (input, nanos) in [
        ("1500ns", 1_500),
        ("1500000ns", 1_500_000),
        ("-1500ns", -1_500),
    ] {
        assert_eq!(
            Duration::from_nanos(nanos).to_string(),
            expected["duration_strings"][input].as_str().unwrap()
        );
    }
    let mut typed = TypedConfig {
        optional: None,
        maximum: 0,
    };
    apply_env_overrides_from(
        &mut typed,
        "APP",
        [
            ("APP_OPTIONAL", "123"),
            ("APP_MAXIMUM", "18446744073709551615"),
        ],
    )
    .unwrap();
    assert_eq!(
        typed.optional.as_deref(),
        expected["optional_string"].as_str()
    );
    assert_eq!(typed.maximum, expected["maximum_u64"].as_u64().unwrap());
}

#[test]
fn cfg_005_zero_toml_values_do_not_override_defaults() {
    let expected = fixture("CFG-005");
    let file = tempfile_dir().join("zero.toml");
    std::fs::write(
        &file,
        "debug = false\ntimeout = 0\nrate = 0.0\nname = \"\"\n[server]\nport = 0\nhost = \"\"\n",
    )
    .unwrap();
    let mut config = defaults();
    merge_file(&mut config, &file).unwrap();
    assert_eq!(config, defaults());
    assert!(expected["zero_preserved"].as_bool().unwrap());
}

#[test]
fn cfg_006_map_fields_reject_and_env_overrides_are_ignored() {
    let expected = fixture("CFG-006");
    let file = tempfile_dir().join("map.toml");
    std::fs::write(&file, "[allowed]\nadmin = 3\n").unwrap();
    let error = merge_file(&mut nonempty_map_defaults(), &file).unwrap_err();
    assert!(error.to_string().contains("allowed"));
    assert!(expected["map_error"].as_bool().unwrap());
    assert!(expected["map_mentions_field"].as_bool().unwrap());
    let mut config = nonempty_map_defaults();
    apply_env_overrides_from(&mut config, "APP", [("APP_ALLOWED_EXISTING", "4")]).unwrap();
    assert_eq!(config.allowed.get("existing"), Some(&1));
    assert!(expected["env_map_unchanged"].as_bool().unwrap());
}

#[cfg(windows)]
#[test]
fn cfg_001_windows_prefers_userprofile() {
    let expected = fixture("CFG-001");
    assert_eq!(expected["windows_home_env"], "USERPROFILE");
    let path = default_path_for_roots(
        "symx",
        None,
        Some(PathBuf::from(r"C:\wrong-home")),
        Some(PathBuf::from(r"C:\expected-home")),
    );
    assert!(path.starts_with(r"C:\expected-home"));
}

#[test]
fn cfg_007_loader_caches_reload_and_reset() {
    let expected = fixture("CFG-007");
    let loader = Loader::new(Options::new("rust-foundation-cache-test"), defaults);
    let first = loader.load().unwrap();
    let second = loader.load().unwrap();
    assert!(Arc::ptr_eq(&first, &second));
    let reloaded = loader.reload().unwrap();
    assert!(!Arc::ptr_eq(&first, &reloaded));
    loader.reset_cache();
    let reset = loader.load().unwrap();
    assert!(!Arc::ptr_eq(&reloaded, &reset));
    assert!(expected["load_same"].as_bool().unwrap());
    assert!(expected["reload_new"].as_bool().unwrap());
    assert!(expected["reset_new"].as_bool().unwrap());
}
