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
    let agent = ureq::Agent::new_with_defaults();
    let mut response = match agent.get(url).call() {
        Ok(response) => response,
        Err(error) => {
            return Outcome {
                release: None,
                error: Some(error.to_string()),
            };
        }
    };
    if response.status().as_u16() >= 300 {
        return Outcome {
            release: None,
            error: Some(format!("HTTP {}", response.status().as_u16())),
        };
    }
    let raw = match response.body_mut().read_to_string() {
        Ok(raw) => raw,
        Err(error) => {
            return Outcome {
                release: None,
                error: Some(error.to_string()),
            };
        }
    };
    let Some(tag_name) = json_string(&raw, "tag_name") else {
        return Outcome {
            release: None,
            error: Some("response missing tag_name".to_owned()),
        };
    };
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
    let timestamp = json_string(&raw, "timestamp")?;
    let created = parse_rfc3339_ms(&timestamp)?;
    let start = raw.find("\"release\":")? + "\"release\":".len();
    let release_raw = &raw[start..];
    let end = matching_object_end(release_raw)?;
    let response = release_raw[..=end].to_owned();
    let tag_name = json_string(&response, "tag_name")?;
    Some((created, CachedRelease { tag_name, response }))
}

fn write_cache(path: &Path, now_ms: u128, release: &CachedRelease) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let raw = format!(
        "{{\"timestamp\":\"{}\",\"release\":{}}}",
        format_rfc3339_ms(now_ms),
        release.response
    );
    fs::write(path, raw)
}

fn json_string(raw: &str, key: &str) -> Option<String> {
    let marker = format!("\"{key}\":\"");
    let rest = raw.get(raw.find(&marker)? + marker.len()..)?;
    let mut value = String::new();
    let mut escaped = false;
    for ch in rest.chars() {
        if escaped {
            value.push(match ch {
                'n' => '\n',
                'r' => '\r',
                't' => '\t',
                other => other,
            });
            escaped = false;
        } else if ch == '\\' {
            escaped = true;
        } else if ch == '"' {
            return Some(value);
        } else {
            value.push(ch);
        }
    }
    None
}

fn matching_object_end(raw: &str) -> Option<usize> {
    let mut depth = 0;
    let mut quoted = false;
    let mut escaped = false;
    for (index, ch) in raw.char_indices() {
        if quoted {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                quoted = false;
            }
        } else if ch == '"' {
            quoted = true;
        } else if ch == '{' {
            depth += 1;
        } else if ch == '}' {
            depth -= 1;
            if depth == 0 {
                return Some(index);
            }
        }
    }
    None
}

fn parse_rfc3339_ms(value: &str) -> Option<u128> {
    let year: i64 = value.get(0..4)?.parse().ok()?;
    let month: i64 = value.get(5..7)?.parse().ok()?;
    let day: i64 = value.get(8..10)?.parse().ok()?;
    let hour: u128 = value.get(11..13)?.parse().ok()?;
    let minute: u128 = value.get(14..16)?.parse().ok()?;
    let second: u128 = value.get(17..19)?.parse().ok()?;
    let fraction = value.get(19..)?.trim_end_matches('Z');
    let millis = if let Some(digits) = fraction.strip_prefix('.') {
        let mut padded = digits.chars().take(3).collect::<String>();
        while padded.len() < 3 {
            padded.push('0');
        }
        padded.parse().ok()?
    } else {
        0
    };
    let y = year - i64::from(month <= 2);
    let era = y.div_euclid(400);
    let yoe = y - era * 400;
    let doy = (153 * (month + if month > 2 { -3 } else { 9 }) + 2) / 5 + day - 1;
    let days = era * 146097 + yoe * 365 + yoe / 4 - yoe / 100 + doy - 719468;
    Some(((days as u128 * 24 + hour) * 60 + minute) * 60_000 + second * 1000 + millis)
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
