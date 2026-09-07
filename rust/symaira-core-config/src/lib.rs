#![deny(unsafe_code)]

//! Generic TOML configuration loading with Go-compatible precedence and overrides.

use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::{Number, Value};
use std::env;
use std::fmt;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use thiserror::Error;

/// Configuration loader options.
#[derive(Clone, Debug, Default)]
pub struct Options {
    pub app_name: String,
    pub env_prefix: Option<String>,
    pub config_name: Option<String>,
    pub use_legacy_config_path: bool,
}

impl Options {
    pub fn new(app_name: impl Into<String>) -> Self {
        Self {
            app_name: app_name.into(),
            ..Self::default()
        }
    }

    pub fn config_name(mut self, name: impl Into<String>) -> Self {
        self.config_name = Some(name.into());
        self
    }

    pub fn env_prefix(mut self, prefix: impl Into<String>) -> Self {
        self.env_prefix = Some(prefix.into());
        self
    }

    pub fn use_legacy_config_path(mut self, enabled: bool) -> Self {
        self.use_legacy_config_path = enabled;
        self
    }

    fn resolved_config_name(&self) -> &str {
        self.config_name.as_deref().unwrap_or(&self.app_name)
    }

    fn resolved_prefix(&self) -> String {
        self.env_prefix
            .clone()
            .unwrap_or_else(|| self.app_name.to_ascii_uppercase())
    }
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("{message}")]
pub struct ConfigError {
    message: String,
}

impl ConfigError {
    fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
        }
    }
}

/// Structural metadata needed because stable Rust has no runtime equivalent
/// of Go reflection for distinguishing nested structs from map fields.
pub trait ConfigSchema {
    /// Dot-separated JSON-tag paths whose fields are maps. TOML values for
    /// these paths are rejected and environment overrides are ignored.
    fn map_fields() -> &'static [&'static str];

    /// Paths whose nullable representation is semantically a string.
    fn string_fields() -> &'static [&'static str] {
        &[]
    }

    /// Paths whose numeric representation uses the unsigned integer domain.
    fn unsigned_fields() -> &'static [&'static str] {
        &[]
    }
}

/// Return the global config path, honoring only absolute XDG_CONFIG_HOME.
pub fn default_path(app_name: &str) -> PathBuf {
    default_path_for_roots(
        app_name,
        env::var_os("XDG_CONFIG_HOME").map(PathBuf::from),
        env::var_os("HOME").map(PathBuf::from),
        env::var_os("USERPROFILE").map(PathBuf::from),
    )
}

/// Deterministic path-resolution seam used by native contract tests.
pub fn default_path_for_roots(
    app_name: &str,
    xdg: Option<PathBuf>,
    home: Option<PathBuf>,
    userprofile: Option<PathBuf>,
) -> PathBuf {
    if let Some(path) = xdg.filter(|path| path.is_absolute()) {
        return path.join(app_name).join("config.toml");
    }
    platform_home(home, userprofile)
        .map(|home| home.join(".config").join(app_name).join("config.toml"))
        .unwrap_or_else(|| PathBuf::from(".config").join(app_name).join("config.toml"))
}

fn home_dir() -> Option<PathBuf> {
    platform_home(
        env::var_os("HOME").map(PathBuf::from),
        env::var_os("USERPROFILE").map(PathBuf::from),
    )
}

fn platform_home(home: Option<PathBuf>, userprofile: Option<PathBuf>) -> Option<PathBuf> {
    #[cfg(windows)]
    let selected = userprofile
        .filter(|path| !path.as_os_str().is_empty())
        .or(home);
    #[cfg(not(windows))]
    let selected = {
        let _ = userprofile;
        home
    };
    selected.filter(|path| !path.as_os_str().is_empty())
}

/// Cached loader. `load` caches the first result; `reload` bypasses that cache.
pub struct Loader<T> {
    options: Options,
    defaults: Arc<dyn Fn() -> T + Send + Sync>,
    cache: Mutex<Option<Result<Arc<T>, ConfigError>>>,
}

impl<T> fmt::Debug for Loader<T> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Loader")
            .field("options", &self.options)
            .finish_non_exhaustive()
    }
}

impl<T> Loader<T>
where
    T: Clone + ConfigSchema + Serialize + DeserializeOwned + Send + Sync + 'static,
{
    pub fn new<F>(options: Options, defaults: F) -> Self
    where
        F: Fn() -> T + Send + Sync + 'static,
    {
        Self {
            options,
            defaults: Arc::new(defaults),
            cache: Mutex::new(None),
        }
    }

    pub fn load(&self) -> Result<Arc<T>, ConfigError> {
        let mut cache = self.cache.lock().expect("config cache mutex poisoned");
        if let Some(result) = &*cache {
            return result.clone();
        }
        let result = self.load_once().map(Arc::new);
        *cache = Some(result.clone());
        result
    }

    pub fn reload(&self) -> Result<Arc<T>, ConfigError> {
        self.load_once().map(Arc::new)
    }

    pub fn reset_cache(&self) {
        let mut cache = self.cache.lock().expect("config cache mutex poisoned");
        *cache = None;
    }

    pub fn options(&self) -> &Options {
        &self.options
    }

    fn load_once(&self) -> Result<T, ConfigError> {
        if home_dir().is_none() {
            return Err(ConfigError::new("cannot determine home directory"));
        }
        let mut config = (self.defaults)();
        let global_path = if self.options.use_legacy_config_path {
            home_dir()
                .expect("home checked above")
                .join(".config")
                .join(self.options.resolved_config_name())
                .join("config.toml")
        } else {
            default_path(self.options.resolved_config_name())
        };
        merge_file(&mut config, &global_path)
            .map_err(|error| ConfigError::new(format!("global config error: {error}")))?;
        if let Ok(cwd) = env::current_dir() {
            let project = cwd.join(format!(".{}.toml", self.options.resolved_config_name()));
            merge_file(&mut config, &project)
                .map_err(|error| ConfigError::new(format!("project config error: {error}")))?;
        }
        apply_env_overrides(&mut config, &self.options.resolved_prefix())
            .map_err(|error| ConfigError::new(format!("env override error: {error}")))?;
        Ok(config)
    }
}

/// Merge a TOML file into a config value. Missing files are intentionally ignored.
pub fn merge_file<T>(config: &mut T, path: &Path) -> Result<(), ConfigError>
where
    T: ConfigSchema + Serialize + DeserializeOwned,
{
    let text = match fs::read_to_string(path) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => {
            return Err(ConfigError::new(format!(
                "cannot read {}: {error}",
                path.display()
            )));
        }
    };
    let toml_value: toml::Value = toml::from_str(&text).map_err(|error| {
        ConfigError::new(format!("failed to parse {}: {error}", path.display()))
    })?;
    let overlay = serde_json::to_value(toml_value)
        .map_err(|error| ConfigError::new(format!("convert TOML {}: {error}", path.display())))?;
    let mut current = serde_json::to_value(&*config)
        .map_err(|error| ConfigError::new(format!("encode defaults: {error}")))?;
    if let Some(field) = unsupported_map_field(&current, &overlay, "", T::map_fields()) {
        return Err(ConfigError::new(format!(
            "field {field:?}: map fields are not supported from config"
        )));
    }
    if let Some(field) = incompatible_field(&current, &overlay, "") {
        return Err(ConfigError::new(format!(
            "field {field:?}: incompatible TOML value"
        )));
    }
    merge_nonzero(&mut current, &overlay);
    *config = serde_json::from_value(current)
        .map_err(|error| ConfigError::new(format!("apply {}: {error}", path.display())))?;
    Ok(())
}

/// Apply `{PREFIX}_{FIELD}` and `{PREFIX}_{SECTION}_{FIELD}` environment values.
pub fn apply_env_overrides<T>(config: &mut T, prefix: &str) -> Result<(), ConfigError>
where
    T: ConfigSchema + Serialize + DeserializeOwned,
{
    let environment: std::collections::BTreeMap<_, _> = env::vars().collect();
    apply_env_overrides_from(config, prefix, &environment)
}

/// Apply overrides from an explicit environment snapshot. This is the safe,
/// deterministic seam used by cross-language tests and embedders.
pub fn apply_env_overrides_from<T, I, K, V>(
    config: &mut T,
    prefix: &str,
    environment: I,
) -> Result<(), ConfigError>
where
    T: ConfigSchema + Serialize + DeserializeOwned,
    I: IntoIterator<Item = (K, V)>,
    K: Into<String>,
    V: Into<String>,
{
    let environment: std::collections::BTreeMap<String, String> = environment
        .into_iter()
        .map(|(key, value)| (key.into(), value.into()))
        .collect();
    let mut current = serde_json::to_value(&*config)
        .map_err(|error| ConfigError::new(format!("encode config: {error}")))?;
    apply_env_value(
        &mut current,
        prefix,
        &environment,
        "",
        T::map_fields(),
        T::string_fields(),
        T::unsigned_fields(),
    )?;
    *config = serde_json::from_value(current)
        .map_err(|error| ConfigError::new(format!("decode env overrides: {error}")))?;
    Ok(())
}

fn unsupported_map_field(
    current: &Value,
    overlay: &Value,
    path: &str,
    map_fields: &[&str],
) -> Option<String> {
    let (Value::Object(current), Value::Object(overlay)) = (current, overlay) else {
        return None;
    };
    for (key, value) in overlay {
        let child_path = join_path(path, key);
        if map_fields.contains(&child_path.as_str()) {
            return Some(child_path);
        }
        let Some(existing) = current.get(key) else {
            continue;
        };
        let nested_map = matches!((existing, value), (Value::Object(_), Value::Object(_)))
            .then(|| unsupported_map_field(existing, value, &child_path, map_fields))
            .flatten();
        if let Some(field) = nested_map {
            return Some(field);
        }
    }
    None
}

fn incompatible_field(current: &Value, overlay: &Value, path: &str) -> Option<String> {
    if overlay.is_null() || current.is_null() {
        return None;
    }
    match (current, overlay) {
        (Value::Object(current), Value::Object(overlay)) => {
            overlay.iter().find_map(|(key, value)| {
                current
                    .get(key)
                    .and_then(|existing| incompatible_field(existing, value, &join_path(path, key)))
            })
        }
        (Value::Array(current), Value::Array(overlay)) => current
            .first()
            .zip(overlay.first())
            .and_then(|(existing, value)| incompatible_field(existing, value, path)),
        (Value::Bool(_), Value::Bool(_))
        | (Value::Number(_), Value::Number(_))
        | (Value::String(_), Value::String(_)) => None,
        _ => Some(path.to_string()),
    }
}

fn join_path(parent: &str, child: &str) -> String {
    if parent.is_empty() {
        child.to_string()
    } else {
        format!("{parent}.{child}")
    }
}

fn merge_nonzero(current: &mut Value, overlay: &Value) {
    match (current, overlay) {
        (Value::Object(current), Value::Object(overlay)) => {
            for (key, value) in overlay {
                if value.is_null() {
                    continue;
                }
                if let Some(existing) = current.get_mut(key) {
                    merge_nonzero(existing, value);
                }
            }
        }
        (current, overlay) if current.is_null() || is_nonzero(overlay) => {
            *current = overlay.clone()
        }
        _ => {}
    }
}

fn is_nonzero(value: &Value) -> bool {
    match value {
        Value::Null => false,
        Value::Bool(value) => *value,
        Value::Number(value) => value.as_f64().is_some_and(|number| number != 0.0),
        Value::String(value) => !value.is_empty(),
        Value::Array(_) | Value::Object(_) => true,
    }
}

fn apply_env_value(
    value: &mut Value,
    prefix: &str,
    environment: &std::collections::BTreeMap<String, String>,
    path: &str,
    map_fields: &[&str],
    string_fields: &[&str],
    unsigned_fields: &[&str],
) -> Result<(), ConfigError> {
    let Value::Object(fields) = value else {
        return Ok(());
    };
    let keys: Vec<String> = fields.keys().cloned().collect();
    for key in keys {
        let child_path = join_path(path, &key);
        let env_key = format!("{prefix}_{}", key.to_ascii_uppercase());
        let field = fields.get_mut(&key).expect("key collected from object");
        if map_fields.contains(&child_path.as_str()) {
            continue;
        } else if field.is_object() {
            apply_env_value(
                field,
                &env_key,
                environment,
                &child_path,
                map_fields,
                string_fields,
                unsigned_fields,
            )?;
        } else if let Some(raw) = environment.get(&env_key) {
            if raw.is_empty() {
                continue;
            }
            *field = parse_env_value(raw, field, &child_path, string_fields, unsigned_fields)
                .map_err(|error| ConfigError::new(format!("env {env_key}: {error}")))?;
        }
    }
    Ok(())
}

fn parse_env_value(
    raw: &str,
    template: &Value,
    path: &str,
    string_fields: &[&str],
    unsigned_fields: &[&str],
) -> Result<Value, String> {
    if string_fields.contains(&path) {
        return Ok(Value::String(raw.to_string()));
    }
    if unsigned_fields.contains(&path) {
        return raw
            .parse::<u64>()
            .map(|value| Value::Number(value.into()))
            .map_err(|error| format!("cannot parse {raw:?} as uint: {error}"));
    }
    match template {
        Value::Bool(_) => match raw {
            "1" | "t" | "T" | "true" | "TRUE" | "True" => Ok(Value::Bool(true)),
            "0" | "f" | "F" | "false" | "FALSE" | "False" => Ok(Value::Bool(false)),
            _ => Err(format!("cannot parse {raw:?} as bool")),
        },
        Value::Number(number) if number.is_i64() || number.is_u64() => raw
            .parse::<i64>()
            .map(|value| Value::Number(value.into()))
            .map_err(|error| format!("cannot parse {raw:?} as int: {error}")),
        Value::Number(_) => raw
            .parse::<f64>()
            .map_err(|error| format!("cannot parse {raw:?} as float: {error}"))
            .and_then(|value| {
                Number::from_f64(value)
                    .map(Value::Number)
                    .ok_or_else(|| "non-finite float".to_string())
            }),
        Value::Array(items) => {
            let empty = Value::String(String::new());
            let template = items.first().unwrap_or(&empty);
            raw.split(',')
                .map(str::trim)
                .map(|item| parse_env_value(item, template, path, string_fields, unsigned_fields))
                .collect::<Result<Vec<_>, _>>()
                .map(Value::Array)
        }
        Value::Null => {
            if matches!(
                raw,
                "1" | "t"
                    | "T"
                    | "true"
                    | "TRUE"
                    | "True"
                    | "0"
                    | "f"
                    | "F"
                    | "false"
                    | "FALSE"
                    | "False"
            ) {
                Ok(Value::Bool(matches!(
                    raw,
                    "1" | "t" | "T" | "true" | "TRUE" | "True"
                )))
            } else if let Ok(value) = raw.parse::<i64>() {
                Ok(Value::Number(value.into()))
            } else if let Ok(value) = raw.parse::<f64>() {
                Number::from_f64(value)
                    .map(Value::Number)
                    .ok_or_else(|| "non-finite float".to_string())
            } else {
                Ok(Value::String(raw.to_string()))
            }
        }
        Value::String(_) => Ok(Value::String(raw.to_string())),
        Value::Object(_) => Err("object values are not supported from environment".to_string()),
    }
}

/// Signed nanoseconds with Go `time.Duration` parsing and formatting semantics.
///
/// An unsigned `std::time::Duration` cannot represent the negative values that
/// Go accepts, so configuration APIs use this explicit signed domain instead.
#[derive(Clone, Copy, Debug, Default, Eq, Ord, PartialEq, PartialOrd)]
pub struct Duration(i64);

impl Duration {
    pub const fn from_nanos(nanos: i64) -> Self {
        Self(nanos)
    }

    pub const fn as_nanos(self) -> i64 {
        self.0
    }
}

impl fmt::Display for Duration {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&duration::format_duration(*self))
    }
}

/// Serde adapter for Go-style signed duration strings such as `-2.5s`.
pub mod duration {
    use super::Duration;
    use serde::{Deserialize, Deserializer, Serializer};

    pub fn serialize<S>(value: &Duration, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_str(&format_duration(*value))
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Duration, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = String::deserialize(deserializer)?;
        parse_duration(&value).map_err(serde::de::Error::custom)
    }

    pub fn parse_duration(input: &str) -> Result<Duration, String> {
        if input.is_empty() {
            return Err("duration is empty".to_string());
        }
        let (negative, mut rest) = match input.as_bytes()[0] {
            b'+' => (false, &input[1..]),
            b'-' => (true, &input[1..]),
            _ => (false, input),
        };
        if rest.is_empty() {
            return Err(format!("invalid duration {input:?}"));
        }
        let mut total: i128 = 0;
        while !rest.is_empty() {
            let number_end = rest
                .find(|character: char| !character.is_ascii_digit() && character != '.')
                .unwrap_or(rest.len());
            let number = &rest[..number_end];
            if number.is_empty() || number == "." {
                return Err(format!("invalid duration {input:?}"));
            }
            let unit_start = number_end;
            let unit_end = rest[unit_start..]
                .find(|character: char| character.is_ascii_digit() || character == '.')
                .map_or(rest.len(), |offset| unit_start + offset);
            let unit = &rest[unit_start..unit_end];
            let multiplier: i128 = match unit {
                "ns" => 1,
                "us" | "µs" | "μs" => 1_000,
                "ms" => 1_000_000,
                "s" => 1_000_000_000,
                "m" => 60 * 1_000_000_000,
                "h" => 3_600 * 1_000_000_000,
                _ => return Err(format!("invalid duration unit {unit:?}")),
            };
            let (whole, fraction) = number.split_once('.').unwrap_or((number, ""));
            if whole.is_empty() && fraction.is_empty() {
                return Err(format!("invalid duration {input:?}"));
            }
            if !whole.chars().all(|c| c.is_ascii_digit())
                || !fraction.chars().all(|c| c.is_ascii_digit())
            {
                return Err(format!("invalid duration {input:?}"));
            }
            let digits = format!("{whole}{fraction}");
            let numerator: i128 = digits
                .parse()
                .map_err(|_| format!("duration overflow for {input:?}"))?;
            let scale = 10_i128
                .checked_pow(fraction.len() as u32)
                .ok_or_else(|| "duration overflow".to_string())?;
            let nanos = numerator
                .checked_mul(multiplier)
                .ok_or_else(|| "duration overflow".to_string())?
                / scale;
            total = total
                .checked_add(nanos)
                .ok_or_else(|| "duration overflow".to_string())?;
            rest = &rest[unit_end..];
        }
        let signed = if negative { -total } else { total };
        i64::try_from(signed)
            .map(Duration)
            .map_err(|_| "duration overflow".to_string())
    }

    pub fn format_duration(value: Duration) -> String {
        let nanos = i128::from(value.0);
        if nanos == 0 {
            return "0s".to_string();
        }
        let sign = if nanos < 0 { "-" } else { "" };
        let mut absolute = nanos.abs();
        if absolute < 1_000_000_000 {
            return if absolute < 1_000 {
                format!("{sign}{absolute}ns")
            } else if absolute < 1_000_000 {
                format_subsecond(sign, absolute, 1_000, 3, "µs")
            } else {
                format_subsecond(sign, absolute, 1_000_000, 6, "ms")
            };
        }
        let hours = absolute / 3_600_000_000_000;
        absolute %= 3_600_000_000_000;
        let minutes = absolute / 60_000_000_000;
        absolute %= 60_000_000_000;
        let seconds = absolute / 1_000_000_000;
        let fraction = absolute % 1_000_000_000;
        let mut output = sign.to_string();
        if hours > 0 {
            output.push_str(&format!("{hours}h"));
        }
        if hours > 0 || minutes > 0 {
            output.push_str(&format!("{minutes}m"));
        }
        if fraction == 0 {
            output.push_str(&format!("{seconds}s"));
        } else {
            let mut fraction_text = format!("{fraction:09}");
            while fraction_text.ends_with('0') {
                fraction_text.pop();
            }
            output.push_str(&format!("{seconds}.{fraction_text}s"));
        }
        output
    }

    fn format_subsecond(
        sign: &str,
        nanos: i128,
        unit_nanos: i128,
        precision: usize,
        suffix: &str,
    ) -> String {
        let whole = nanos / unit_nanos;
        let remainder = nanos % unit_nanos;
        if remainder == 0 {
            return format!("{sign}{whole}{suffix}");
        }
        let mut fraction = format!("{remainder:0precision$}");
        while fraction.ends_with('0') {
            fraction.pop();
        }
        format!("{sign}{whole}.{fraction}{suffix}")
    }
}
