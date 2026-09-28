use serde::Deserialize;
use symaira_core_update::{Asset, Response, check_response};

#[derive(Deserialize)]
struct Fixture {
    cases: Vec<Case>,
}

#[derive(Deserialize)]
struct Case {
    id: String,
    current: String,
    response: String,
    result: serde_json::Value,
}

#[test]
fn release_response_outcomes_match_go_checker() {
    let fixture: Fixture = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/update/responses.json"
    ))
    .unwrap();
    assert_eq!(fixture.cases.len(), 9);

    for case in fixture.cases {
        let api: serde_json::Value = serde_json::from_str(&case.response).unwrap();
        let assets = api
            .get("assets")
            .and_then(serde_json::Value::as_array)
            .into_iter()
            .flatten()
            .map(|asset| Asset {
                name: asset
                    .get("name")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default()
                    .to_owned(),
                browser_download_url: asset
                    .get("browser_download_url")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default()
                    .to_owned(),
                size: asset
                    .get("size")
                    .and_then(serde_json::Value::as_i64)
                    .unwrap_or_default(),
            })
            .collect();
        let response = Response {
            draft: api
                .get("draft")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or_default(),
            html_url: api
                .get("html_url")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            prerelease: api
                .get("prerelease")
                .and_then(serde_json::Value::as_bool)
                .unwrap_or_default(),
            tag_name: api
                .get("tag_name")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            body: api
                .get("body")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default()
                .to_owned(),
            assets,
        };
        let actual = match check_response(&case.current, response) {
            Ok(Some(release)) => serde_json::json!({"release": {
                "tag_name": release.tag_name,
                "body": release.body,
                "html_url": release.html_url,
                "assets": release.assets.into_iter().map(|asset| serde_json::json!({
                    "name": asset.name,
                    "browser_download_url": asset.browser_download_url,
                    "size": asset.size,
                })).collect::<Vec<_>>(),
            }, "error": null}),
            Ok(None) => serde_json::json!({"release": null, "error": null}),
            Err(error) => serde_json::json!({"release": null, "error": error}),
        };
        assert_eq!(actual, case.result, "case {}", case.id);
    }
}
