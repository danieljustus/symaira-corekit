use serde::Deserialize;
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
    let fixture: Fixture = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/update/stable-versions.json"
    ))
    .unwrap();
    assert_eq!(fixture.cases.len(), 30);
    for case in fixture.cases {
        let result = update_available(&case.current, &case.latest);
        assert_eq!(result.is_err(), case.invalid_latest, "{:?}", case.current);
        assert_eq!(
            result.unwrap_or(false),
            case.available,
            "{:?}",
            case.current
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
