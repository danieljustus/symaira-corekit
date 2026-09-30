//! Persistent update response cache used by the UPD-003 parity slice.
use std::{fs, path::Path, time::Duration};

/// Default update response lifetime, matching Go's `DefaultCacheTTL`.
pub const DEFAULT_CACHE_TTL: Duration = Duration::from_secs(24 * 60 * 60);

/// A cached decision, retaining the Go release response as JSON.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CachedRelease {
    pub tag_name: String,
    pub response: String,
}

/// Result of one update check.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Outcome {
    pub release: Option<CachedRelease>,
    pub error: Option<String>,
}

/// Checks a loopback or other configured release endpoint with Go-compatible cache semantics.
/// `now_ms` is supplied by the caller so expiry tests need no real-time sleeps.
pub fn check(url: &str, cache_path: &Path, ttl: Duration, force: bool, now_ms: u128) -> Outcome {
    if !force
        && let Some((created, cached)) = read_cache(cache_path)
        && now_ms.saturating_sub(created) < ttl.as_millis()
    {
        return Outcome {
            release: Some(cached),
            error: None,
        };
    }
    let response = match crate::request::fetch(url, "", Duration::from_secs(3)) {
        Ok(response) => response,
        Err(error) => {
            return Outcome {
                release: None,
                error: Some(error.message),
            };
        }
    };
    let raw = match String::from_utf8(response.body) {
        Ok(raw) => raw,
        Err(error) => {
            return Outcome {
                release: None,
                error: Some(error.to_string()),
            };
        }
    };
    let decoded = serde_json::from_str::<serde_json::Value>(&raw);
    let Some(tag_name) = decoded.as_ref().ok().and_then(release_tag) else {
        return Outcome {
            release: None,
            error: Some("response missing tag_name".to_owned()),
        };
    };
    let document = decoded.as_ref().expect("validated release JSON");
    let eligibility = crate::check_response(
        "v0.0.0",
        crate::Response {
            draft: wire_field(document, "draft", "draft")
                .as_bool()
                .unwrap_or(false),
            prerelease: wire_field(document, "prerelease", "prerelease")
                .as_bool()
                .unwrap_or(false),
            tag_name: tag_name.clone(),
            ..crate::Response::default()
        },
    );
    // Only reuse response validation here, not current-version update selection.
    if let Err(error) = eligibility {
        return Outcome {
            release: None,
            error: Some(error),
        };
    }
    let release = CachedRelease {
        tag_name,
        response: raw,
    };
    let _ = write_cache(cache_path, now_ms, &release);
    Outcome {
        release: Some(release),
        error: None,
    }
}

fn read_cache(path: &Path) -> Option<(u128, CachedRelease)> {
    let raw = fs::read_to_string(path).ok()?;
    let document: serde_json::Value = serde_json::from_str(&raw).ok()?;
    let timestamp = wire_field(&document, "timestamp", "timestamp").as_str()?;
    let created = parse_rfc3339_ms(timestamp)?;
    let release = wire_field(&document, "release", "release");
    let tag_name = release_tag(release)?;
    let response = serde_json::to_string(release).ok()?;
    Some((created, CachedRelease { tag_name, response }))
}

fn write_cache(path: &Path, now_ms: u128, release: &CachedRelease) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let response: serde_json::Value =
        serde_json::from_str(&release.response).map_err(std::io::Error::other)?;
    let assets: Vec<_> = wire_field(&response, "assets", "Assets")
        .as_array().into_iter().flatten().map(|asset| serde_json::json!({
            "Name": wire_field(asset, "name", "Name").as_str().unwrap_or_default(),
            "BrowserDownloadURL": wire_field(asset, "browser_download_url", "BrowserDownloadURL").as_str().unwrap_or_default(),
            "Size": wire_field(asset, "size", "Size").as_i64().unwrap_or_default(),
        })).collect();
    // Go persists Release fields, not the GitHub response's snake_case keys.
    let disk = serde_json::json!({
        "timestamp": format_rfc3339_ms(now_ms),
        "release": {
            "TagName": release.tag_name,
            "Body": wire_field(&response, "body", "Body").as_str().unwrap_or_default(),
            "HTMLURL": wire_field(&response, "html_url", "HTMLURL").as_str().unwrap_or_default().trim(),
            "Assets": assets,
        },
    });
    fs::write(
        path,
        serde_json::to_vec(&disk).map_err(std::io::Error::other)?,
    )
}

fn wire_field<'a>(value: &'a serde_json::Value, api: &str, disk: &str) -> &'a serde_json::Value {
    value
        .as_object()
        .and_then(|object| {
            object
                .iter()
                .find(|(key, _)| key.eq_ignore_ascii_case(api) || key.eq_ignore_ascii_case(disk))
        })
        .map_or(&serde_json::Value::Null, |(_, value)| value)
}

fn release_tag(value: &serde_json::Value) -> Option<String> {
    let object = value.as_object()?;
    for (key, value) in object {
        if value.is_null() {
            continue;
        }
        match key.to_ascii_lowercase().as_str() {
            "tag_name" | "tagname" | "body" | "html_url" | "htmlurl" => {
                value.as_str()?;
            }
            "draft" | "prerelease" => {
                value.as_bool()?;
            }
            "assets" => {
                for asset in value.as_array()? {
                    if asset.is_null() {
                        continue;
                    }
                    for (key, value) in asset.as_object()? {
                        if value.is_null() {
                            continue;
                        }
                        match key.to_ascii_lowercase().as_str() {
                            "name" | "browser_download_url" | "browserdownloadurl" => {
                                value.as_str()?;
                            }
                            "size" => {
                                value.as_i64()?;
                            }
                            _ => {}
                        }
                    }
                }
            }
            _ => {}
        }
    }
    let tag = object
        .iter()
        .find(|(key, _)| {
            key.eq_ignore_ascii_case("tag_name") || key.eq_ignore_ascii_case("TagName")
        })?
        .1
        .as_str()?
        .trim();
    if tag.is_empty() {
        None
    } else {
        Some(tag.to_owned())
    }
}

fn parse_rfc3339_ms(value: &str) -> Option<u128> {
    for range in [0..4, 5..7, 8..10, 11..13, 14..16, 17..19] {
        if !value.get(range)?.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
    }
    if value.get(4..5)? != "-"
        || value.get(7..8)? != "-"
        || value.get(10..11)? != "T"
        || value.get(13..14)? != ":"
        || value.get(16..17)? != ":"
    {
        return None;
    }
    let year: i64 = value.get(0..4)?.parse().ok()?;
    let month: i64 = value.get(5..7)?.parse().ok()?;
    let day: i64 = value.get(8..10)?.parse().ok()?;
    let hour: u128 = value.get(11..13)?.parse().ok()?;
    let minute: u128 = value.get(14..16)?.parse().ok()?;
    let second: u128 = value.get(17..19)?.parse().ok()?;
    let tail = value.get(19..)?;
    let (fraction, offset_seconds) = if let Some(fraction) = tail.strip_suffix('Z') {
        (fraction, 0i64)
    } else {
        let start = tail.find(['+', '-'])?;
        let offset = tail.get(start..)?;
        if offset.len() != 6 || offset.get(3..4)? != ":" {
            return None;
        }
        if !offset
            .get(1..3)?
            .bytes()
            .chain(offset.get(4..6)?.bytes())
            .all(|byte| byte.is_ascii_digit())
        {
            return None;
        }
        let hours: i64 = offset.get(1..3)?.parse().ok()?;
        let minutes: i64 = offset.get(4..6)?.parse().ok()?;
        if hours > 23 || minutes > 59 {
            return None;
        }
        let sign = if offset.starts_with('-') { -1 } else { 1 };
        (&tail[..start], sign * (hours * 3600 + minutes * 60))
    };
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let max_day = match month {
        2 => {
            if leap {
                29
            } else {
                28
            }
        }
        4 | 6 | 9 | 11 => 30,
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        _ => return None,
    };
    if !(1..=max_day).contains(&day) || hour > 23 || minute > 59 || second > 59 {
        return None;
    }
    let millis = if let Some(digits) = fraction.strip_prefix('.') {
        if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        let mut padded = digits.chars().take(3).collect::<String>();
        while padded.len() < 3 {
            padded.push('0');
        }
        padded.parse().ok()?
    } else if fraction.is_empty() {
        0
    } else {
        return None;
    };
    let y = year - i64::from(month <= 2);
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
    let days = era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719468;
    let seconds = i128::from(days)
        .checked_mul(86400)?
        .checked_add(i128::try_from(hour * 3600 + minute * 60 + second).ok()?)?
        .checked_sub(i128::from(offset_seconds))?;
    u128::try_from(seconds.checked_mul(1000)?.checked_add(millis)?).ok()
}

fn format_rfc3339_ms(ms: u128) -> String {
    let seconds = (ms / 1000) as i64;
    let days = seconds.div_euclid(86400);
    let daytime = seconds.rem_euclid(86400);
    let z = days + 719468;
    let era = z.div_euclid(146097);
    let doe = z - era * 146097;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let mut year = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{:03}Z",
        daytime / 3600,
        daytime % 3600 / 60,
        daytime % 60,
        ms % 1000
    )
}
