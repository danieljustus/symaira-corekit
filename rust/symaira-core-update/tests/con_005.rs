use std::time::Duration;

use serde_json::Value;
use symaira_core_update::{Response, cache::DEFAULT_CACHE_TTL, check_response, update_available};

#[test]
fn con_005_update_invariants_match_contract_fixture() {
    let fixture: Value = serde_json::from_slice(include_bytes!(
        "../../test-support/symaira-contract-fixtures/fixtures/contracts/update_check_invariants.json"
    ))
    .unwrap();
    assert_eq!(
        DEFAULT_CACHE_TTL,
        Duration::from_secs(fixture["cache_ttl_hours"].as_u64().unwrap() * 60 * 60)
    );

    let markers = fixture["prerelease_and_build_metadata_markers"]
        .as_array()
        .unwrap();
    assert_eq!(fixture["prerelease_and_build_metadata_rejected"], true);
    for marker in markers {
        let version = format!("1.2.3{}suffix", marker.as_str().unwrap());
        assert_eq!(
            update_available("1.2.2", &version),
            Err("latest release tag is not a stable semantic version")
        );
    }
    assert_eq!(update_available("v1.2.3", "1.2.4"), Ok(true));
    assert_eq!(fixture["semver_prefix_optional"], "v");

    assert_eq!(fixture["api_draft_and_prerelease_rejected"], true);
    for (draft, prerelease) in [(true, false), (false, true)] {
        let result = check_response(
            "1.0.0",
            Response {
                draft,
                prerelease,
                tag_name: "v1.1.0".into(),
                ..Response::default()
            },
        );
        assert!(result.is_err(), "release flags must surface to the caller");
    }
    assert_eq!(fixture["api_invalid_tag_rejected"], true);
    assert!(
        check_response(
            "1.0.0",
            Response {
                tag_name: "not-semver".into(),
                ..Response::default()
            }
        )
        .is_err()
    );

    let suppress_v0_gap = fixture["v0_major_gap_suppressed"].as_bool().unwrap();
    assert_eq!(update_available("0.9.0", "1.0.0"), Ok(!suppress_v0_gap));
    assert_eq!(fixture["check_failure_behavior"], "surfaced_to_caller");
}
