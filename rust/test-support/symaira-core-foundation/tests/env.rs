use symaira_core_env::{Environment, getenv_lossy, unsetenv};

static PROCESS_ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn fixture(id: &str) -> serde_json::Value {
    symaira_contract_fixtures::json(symaira_contract_fixtures::foundation(id))
}

#[test]
fn env_001_primary_and_ordered_aliases_are_fixture_backed() {
    let _guard = PROCESS_ENV_LOCK.lock().unwrap();
    let expected = fixture("ENV-001");
    let environment = Environment::from_pairs([
        ("PRIMARY", expected["primary"].as_str().unwrap()),
        ("OLD_ONE", expected["alias"].as_str().unwrap()),
        ("EMPTY", ""),
    ]);
    assert_eq!(environment.getenv("PRIMARY", &["OLD_ONE"]), Some("primary"));
    assert_eq!(
        environment.getenv("MISSING", &["OLD_ONE"]),
        Some("alias-one")
    );
    assert_eq!(getenv_lossy("RUST002_MISSING", &["RUST002_NEVER_SET"]), "");
}

#[test]
fn env_002_process_unset_is_explicitly_unsafe_and_owned_environment_stays_safe() {
    let _guard = PROCESS_ENV_LOCK.lock().unwrap();
    let expected = fixture("ENV-002");
    let mut environment = Environment::from_pairs([("TARGET", "gone"), ("OTHER", "kept")]);
    environment.unsetenv("TARGET").unwrap();
    assert!(environment.is_absent("TARGET"));
    assert_eq!(environment.get("OTHER"), Some("kept"));

    // SAFETY: every test in this process that reads or mutates the process
    // environment holds PROCESS_ENV_LOCK for its complete execution.
    unsafe {
        std::env::set_var("RUST002_TARGET", "gone");
        unsetenv("RUST002_TARGET").unwrap();
    }
    assert_eq!(
        std::env::var("RUST002_TARGET").unwrap_or_default(),
        expected["target"].as_str().unwrap()
    );
    assert_eq!(expected["other"], "kept");
}
