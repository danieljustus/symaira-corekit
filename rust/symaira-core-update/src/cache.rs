//! Persistent update response cache used by the UPD-003 parity slice.
use serde::de::{DeserializeSeed, IgnoredAny, MapAccess, SeqAccess, Visitor};
use serde_json::Value;
use std::{
    fs,
    io::{self, Write},
    path::{Component, Path},
    sync::atomic::{AtomicU64, Ordering},
    time::Duration,
};

static CACHE_TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);

#[derive(Clone, Copy)]
enum WireShape {
    Cache,
    ApiRelease,
    DiskRelease,
    ApiAssets,
    DiskAssets,
    ApiAsset,
    DiskAsset,
}

struct WireSeed {
    shape: WireShape,
    value: Value,
}

fn decode_wire(raw: &str, shape: WireShape) -> Result<Value, serde_json::Error> {
    let mut decoder = serde_json::Deserializer::from_str(raw);
    let value = WireSeed {
        shape,
        value: Value::Null,
    }
    .deserialize(&mut decoder)?;
    // Go's network Decoder.Decode consumes one JSON value; disk Unmarshal
    // requires EOF. Keep these contracts separate, including trailing data.
    if matches!(shape, WireShape::Cache) {
        decoder.end()?;
    }
    Ok(finish_wire(value))
}

// Retain Go slice backing elements during decoding, but expose only its length.
// These keys cannot come from input: recognized fields are schema-filtered.
fn finish_wire(value: Value) -> Value {
    match value {
        Value::Object(mut object) => {
            if let Some(Value::Number(length)) = object.remove("$asset_length") {
                let mut assets = object.remove("$asset_backing").unwrap();
                assets
                    .as_array_mut()
                    .unwrap()
                    .truncate(length.as_u64().unwrap() as usize);
                return finish_wire(assets);
            }
            Value::Object(
                object
                    .into_iter()
                    .map(|(key, value)| (key, finish_wire(value)))
                    .collect(),
            )
        }
        Value::Array(assets) => Value::Array(assets.into_iter().map(finish_wire).collect()),
        value => value,
    }
}

impl<'de> DeserializeSeed<'de> for WireSeed {
    type Value = Value;

    fn deserialize<D: serde::Deserializer<'de>>(self, decoder: D) -> Result<Value, D::Error> {
        decoder.deserialize_any(self)
    }
}

impl<'de> Visitor<'de> for WireSeed {
    type Value = Value;

    fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("a Go release/cache object or asset array")
    }

    fn visit_unit<E: serde::de::Error>(self) -> Result<Value, E> {
        // Null resets slices and pointers, but leaves existing struct fields intact.
        Ok(match self.shape {
            WireShape::ApiAsset | WireShape::DiskAsset => {
                Value::Object(self.value.as_object().cloned().unwrap_or_default())
            }
            _ => Value::Null,
        })
    }

    fn visit_seq<S: SeqAccess<'de>>(self, mut sequence: S) -> Result<Value, S::Error> {
        let shape = match self.shape {
            WireShape::ApiAssets => WireShape::ApiAsset,
            WireShape::DiskAssets => WireShape::DiskAsset,
            _ => return Err(serde::de::Error::custom("expected object")),
        };
        let previous = match self.value {
            Value::Array(assets) => assets,
            Value::Object(mut object) => match object.remove("$asset_backing") {
                Some(Value::Array(assets)) => assets,
                _ => Vec::new(),
            },
            _ => Vec::new(),
        };
        let mut assets = Vec::new();
        while let Some(asset) = sequence.next_element_seed(WireSeed {
            shape,
            value: previous.get(assets.len()).cloned().unwrap_or(Value::Null),
        })? {
            assets.push(asset);
        }
        let length = assets.len();
        if length > 0 {
            assets.extend(previous.into_iter().skip(length));
        }
        Ok(serde_json::json!({"$asset_length": length, "$asset_backing": assets}))
    }

    fn visit_map<M: MapAccess<'de>>(self, mut map: M) -> Result<Value, M::Error> {
        use WireShape::{
            ApiAsset, ApiAssets, ApiRelease, Cache, DiskAsset, DiskAssets, DiskRelease,
        };
        if matches!(self.shape, ApiAssets | DiskAssets) {
            return Err(serde::de::Error::custom("expected asset array"));
        }
        let mut object = self.value.as_object().cloned().unwrap_or_default();
        while let Some(key) = map.next_key::<String>()? {
            // Go's Unicode simple fold includes the long s and Kelvin sign.
            let key = key.replace('ſ', "s").replace('K', "k").to_ascii_lowercase();
            let field = match (self.shape, key.as_str()) {
                (Cache, "timestamp") => Some(("timestamp", 0)),
                (Cache, "release") => Some(("release", 3)),
                (ApiRelease, "tag_name") | (DiskRelease, "tagname") => Some(("TagName", 0)),
                (ApiRelease | DiskRelease, "body") => Some(("Body", 0)),
                (ApiRelease, "html_url") | (DiskRelease, "htmlurl") => Some(("HTMLURL", 0)),
                (ApiRelease, "draft") => Some(("draft", 1)),
                (ApiRelease, "prerelease") => Some(("prerelease", 1)),
                (ApiRelease | DiskRelease, "assets") => Some(("Assets", 4)),
                (ApiAsset | DiskAsset, "name") => Some(("Name", 0)),
                (ApiAsset, "browser_download_url") | (DiskAsset, "browserdownloadurl") => {
                    Some(("BrowserDownloadURL", 0))
                }
                (ApiAsset | DiskAsset, "size") => Some(("Size", 2)),
                _ => None,
            };
            let Some((name, kind)) = field else {
                let _: IgnoredAny = map.next_value()?;
                continue;
            };
            let value = match kind {
                0 => map.next_value::<Option<String>>()?.map(Value::String),
                1 => map.next_value::<Option<bool>>()?.map(Value::Bool),
                2 => map
                    .next_value::<Option<i64>>()?
                    .map(|value| Value::Number(value.into())),
                _ => {
                    let shape = if kind == 3 {
                        DiskRelease
                    } else if matches!(self.shape, ApiRelease) {
                        ApiAssets
                    } else {
                        DiskAssets
                    };
                    Some(map.next_value_seed(WireSeed {
                        shape,
                        value: object.remove(name).unwrap_or(Value::Null),
                    })?)
                }
            };
            // Go ignores null scalar assignments, including after an earlier alias.
            if let Some(value) = value {
                object.insert(name.to_owned(), value);
            }
        }
        Ok(Value::Object(object))
    }
}

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
    let decoded = match decode_wire(&raw, WireShape::ApiRelease) {
        Ok(decoded) => decoded,
        Err(error) => {
            return Outcome {
                release: None,
                error: Some(format!("decode latest release response: {error}")),
            };
        }
    };
    let Some(tag_name) = release_tag(&decoded) else {
        return Outcome {
            release: None,
            error: Some("latest release response did not include a tag name".to_owned()),
        };
    };
    let eligibility = crate::check_response(
        "v0.0.0",
        crate::Response {
            draft: wire_field(&decoded, "draft", "draft")
                .as_bool()
                .unwrap_or(false),
            prerelease: wire_field(&decoded, "prerelease", "prerelease")
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
    let document = decode_wire(&raw, WireShape::Cache).ok()?;
    let timestamp = wire_field(&document, "timestamp", "timestamp").as_str()?;
    let created = parse_rfc3339_ms(timestamp)?;
    let release = wire_field(&document, "release", "release");
    let tag_name = release_tag(release)?;
    let response = serde_json::to_string(release).ok()?;
    Some((created, CachedRelease { tag_name, response }))
}

fn write_cache(path: &Path, now_ms: u128, release: &CachedRelease) -> std::io::Result<()> {
    let response =
        decode_wire(&release.response, WireShape::ApiRelease).map_err(std::io::Error::other)?;
    // Serialize Go structs in declaration order, rather than sorted Value maps.
    #[derive(serde::Serialize)]
    struct DiskAsset<'a> {
        #[serde(rename = "Name")]
        name: &'a str,
        #[serde(rename = "BrowserDownloadURL")]
        browser_download_url: &'a str,
        #[serde(rename = "Size")]
        size: i64,
    }
    #[derive(serde::Serialize)]
    struct DiskRelease<'a> {
        #[serde(rename = "TagName")]
        tag_name: &'a str,
        #[serde(rename = "Body")]
        body: &'a str,
        #[serde(rename = "HTMLURL")]
        html_url: &'a str,
        #[serde(rename = "Assets")]
        assets: Vec<DiskAsset<'a>>,
    }
    #[derive(serde::Serialize)]
    struct DiskCache<'a> {
        timestamp: String,
        release: DiskRelease<'a>,
    }
    let assets = wire_field(&response, "assets", "Assets")
        .as_array()
        .into_iter()
        .flatten()
        .map(|asset| DiskAsset {
            name: wire_field(asset, "name", "Name")
                .as_str()
                .unwrap_or_default(),
            browser_download_url: wire_field(asset, "browser_download_url", "BrowserDownloadURL")
                .as_str()
                .unwrap_or_default(),
            size: wire_field(asset, "size", "Size")
                .as_i64()
                .unwrap_or_default(),
        })
        .collect();
    let disk = DiskCache {
        timestamp: format_rfc3339_ms(now_ms),
        release: DiskRelease {
            tag_name: &release.tag_name,
            body: wire_field(&response, "body", "Body")
                .as_str()
                .unwrap_or_default(),
            html_url: wire_field(&response, "html_url", "HTMLURL")
                .as_str()
                .unwrap_or_default()
                .trim(),
            assets,
        },
    };
    // encoding/json.Marshal escapes HTML and JavaScript line separators.
    let raw = serde_json::to_string(&disk)
        .map_err(std::io::Error::other)?
        .replace('&', "\\u0026")
        .replace('<', "\\u003c")
        .replace('>', "\\u003e")
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029");
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    let parent = cache_directory(parent)?;
    let name = path
        .file_name()
        .ok_or_else(|| io::Error::other("missing cache filename"))?;
    atomic_cache_write(&parent, Path::new(name), raw.as_bytes())
}

// Match Go SafeMkdirAll: reject untrusted symlinks and create private parents.
// Existing root-owned system aliases (notably /var on macOS) stay usable.
fn cache_directory(path: &Path) -> io::Result<cap_std::fs::Dir> {
    let absolute = if path.is_absolute() {
        path.to_owned()
    } else {
        std::env::current_dir()?.join(path)
    };
    // filepath.Abs/Clean in Go removes dot components before touching disk.
    let mut cleaned = std::path::PathBuf::new();
    for component in absolute.components() {
        match component {
            Component::ParentDir => {
                cleaned.pop();
            }
            Component::CurDir => {}
            _ => cleaned.push(component),
        }
    }
    let mut current = std::path::PathBuf::new();
    for component in cleaned.components() {
        current.push(component);
        if !matches!(component, Component::Normal(_)) {
            continue;
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::MetadataExt;
                    if metadata.uid() == 0 {
                        current = fs::canonicalize(&current)?;
                        continue;
                    }
                }
                return Err(io::Error::other("cache parent is an untrusted symlink"));
            }
            Ok(metadata) if metadata.is_dir() => {}
            Ok(_) => return Err(io::Error::other("cache parent is not a directory")),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {
                let mut builder = fs::DirBuilder::new();
                builder.recursive(false);
                #[cfg(unix)]
                {
                    use std::os::unix::fs::DirBuilderExt;
                    builder.mode(0o700);
                }
                if let Err(error) = builder.create(&current) {
                    if error.kind() != io::ErrorKind::AlreadyExists {
                        return Err(error);
                    }
                    // A racing creator must still have installed a directory.
                    if !fs::symlink_metadata(&current)?.is_dir() {
                        return Err(error);
                    }
                }
            }
            Err(error) => return Err(error),
        }
    }
    cap_std::fs::Dir::open_ambient_dir(current, cap_std::ambient_authority())
}

fn atomic_cache_write(parent: &cap_std::fs::Dir, name: &Path, bytes: &[u8]) -> io::Result<()> {
    let mut collisions = 0;
    let (temporary, mut file) = loop {
        let sequence = CACHE_TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
        let temporary = format!(".update-cache-{}-{sequence}.tmp", std::process::id());
        let mut options = cap_std::fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match parent.open_with(&temporary, &options) {
            Ok(file) => break (temporary, file),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {
                collisions += 1;
                if collisions == 100 {
                    return Err(error);
                }
            }
            Err(error) => return Err(error),
        }
    };
    let result = (|| {
        #[cfg(unix)]
        {
            use cap_std::fs::PermissionsExt;
            file.set_permissions(cap_std::fs::Permissions::from_mode(0o600))?;
        }
        file.write_all(bytes)?;
        file.sync_all()?;
        drop(file);
        #[cfg(not(windows))]
        return parent.rename(&temporary, parent, name);
        #[cfg(windows)]
        {
            // Match Go's bounded retry for antivirus/indexer sharing conflicts.
            for attempt in 0..10 {
                match parent.rename(&temporary, parent, name) {
                    Ok(()) => return Ok(()),
                    Err(error) if attempt == 9 => return Err(error),
                    Err(_) => std::thread::sleep(Duration::from_millis(10)),
                }
            }
            unreachable!()
        }
    })();
    if result.is_err() {
        let _ = parent.remove_file(&temporary);
    }
    result
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
    // All recognized assignments were type-checked in input order by WireSeed.
    let tag = value.get("TagName")?.as_str()?.trim();
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
    let fraction = if ms.is_multiple_of(1000) {
        String::new()
    } else {
        format!(".{:03}", ms % 1000)
            .trim_end_matches('0')
            .to_owned()
    };
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}{fraction}Z",
        daytime / 3600,
        daytime % 3600 / 60,
        daytime % 60
    )
}

#[cfg(test)]
mod ordered_wire_tests {
    use super::{WireShape, decode_wire};
    use serde_json::json;

    #[test]
    fn ordered_release_cache_and_asset_assignments_match_go_struct_rules() {
        let api = decode_wire(
            r#"{"tag_name":"v1.3.0","BODY":"first","body":"last","Body":null,"assets":[{"NAME":"first","name":"last","Name":null,"SIZE":1,"size":2},null],"TagName":42}"#,
            WireShape::ApiRelease,
        ).unwrap();
        assert_eq!(api["TagName"], "v1.3.0");
        assert_eq!(api["Body"], "last");
        assert_eq!(api["Assets"][0], json!({"Name":"last", "Size":2}));
        assert_eq!(api["Assets"][1], json!({}));
        for body in [
            r#"{"tag_name":false,"tag_name":"v1.3.0"}"#,
            r#"{"draft":"false","draft":false}"#,
            r#"{"assets":[{"size":1.5,"size":2}]}"#,
            r#"{"assets":{},"assets":[]}"#,
        ] {
            assert!(decode_wire(body, WireShape::ApiRelease).is_err(), "{body}");
        }
        let disk = decode_wire(
            r#"{"release":{"TAGNAME":"invalid","Body":"retained","Assets":[{"NAME":"first","name":"last","BrowserDownloadURL":"url","Size":7}]},"RELEASE":{"TagName":"v1.3.0","Body":null},"timestamp":"1970-01-01T00:00:01Z"}"#,
            WireShape::Cache,
        ).unwrap();
        assert_eq!(disk["release"]["TagName"], "v1.3.0");
        assert_eq!(disk["release"]["Body"], "retained");
        assert_eq!(disk["release"]["Assets"][0]["Name"], "last");
        let reset = decode_wire(
            r#"{"release":{"TagName":"old"},"Release":null,"RELEASE":{"Body":"new"}}"#,
            WireShape::Cache,
        )
        .unwrap();
        assert!(reset["release"].get("TagName").is_none());
        let assets = decode_wire(
            r#"{"tag_name":"v1.3.0","assets":[{"name":"old"}],"ASSETS":null}"#,
            WireShape::ApiRelease,
        )
        .unwrap();
        assert!(assets["Assets"].is_null());
    }
}
