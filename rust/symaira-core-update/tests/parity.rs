#[path = "common/static_update.rs"]
mod static_update;

use serde::Deserialize;
use std::path::PathBuf;
use symaira_core_update::{checkable, update_available};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    current: String,
    latest: String,
    available: bool,
    invalid_latest: bool,
    requests: u8,
}

#[test]
fn stable_release_decisions_match_public_go_checker() {
    let default_fixture = static_update::fixture_path("version");
    let fixture_path = std::env::var_os("UPDATE_VERSION_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or(default_fixture);
    let fixture: Fixture = serde_json::from_slice(
        &std::fs::read(&fixture_path).expect("read static Go stable-version fixture"),
    )
    .expect("valid stable-version fixture");
    assert_eq!(fixture.cases.len(), 30, "nonzero complete version corpus");
    for (index, case) in fixture.cases.into_iter().enumerate() {
        let case_id = format!("stable-version-{:03}", index + 1);
        let result = update_available(&case.current, &case.latest);
        assert_eq!(
            result.is_err(),
            case.invalid_latest,
            "{case_id} invalid_latest current {:?}",
            case.current
        );
        assert_eq!(
            result.unwrap_or(false),
            case.available,
            "{case_id} available current {:?}",
            case.current
        );
        // The public Go Check records no request for an invalid running version.
        assert!(
            case.requests <= 1,
            "{case_id} requests current {:?}",
            case.current
        );
        assert_eq!(
            checkable(&case.current),
            case.requests == 1,
            "{case_id} checkable current {:?}",
            case.current
        );
    }
}
