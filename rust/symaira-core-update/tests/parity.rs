#[path = "common/static_update.rs"]
mod static_update;

use serde::Deserialize;
use symaira_core_update::{checkable, update_available};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    current: String,
    latest: String,
    available: bool,
    invalid_latest: bool,
    requests: u8,
}

#[test]
fn stable_release_decisions_match_public_go_checker() {
    let fixture_path = std::env::var_os("UPDATE_VERSION_FIXTURE")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| static_update::fixture_path("version"));
    let fixture: Fixture = serde_json::from_slice(
        &std::fs::read(fixture_path).expect("read frozen Go stable-version observations"),
    )
    .expect("parse frozen Go stable-version observations");
    assert_eq!(fixture.cases.len(), 30);
    for case in fixture.cases {
        let result = update_available(&case.current, &case.latest);
        assert_eq!(
            result.is_err(),
            case.invalid_latest,
            "{} invalid_latest",
            case.id
        );
        assert_eq!(
            result.unwrap_or(false),
            case.available,
            "{} available",
            case.id
        );
        // The public Go Check records no request for an invalid running version.
        assert!(case.requests <= 1, "{:?}", case.current);
        assert_eq!(
            checkable(&case.current),
            case.requests == 1,
            "{:?}",
            case.current
        );
    }
}
