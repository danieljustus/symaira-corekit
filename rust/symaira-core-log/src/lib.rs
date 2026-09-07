#![deny(unsafe_code)]

//! `log/slog`-compatible stderr logging.
//!
//! The default logger uses the current UTC time. Tests and the Go oracle use
//! [`Logger::new_fixed_time`] so timestamp bytes are deterministic; a fixed
//! clock is never silently substituted for the production clock.

use std::env;
use std::io::{self, Write};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};
use tracing::Level;

const FALLBACK_APP: &str = "sym";

type SharedWriter = Arc<Mutex<Box<dyn Write + Send>>>;

#[derive(Clone)]
pub struct Logger {
    writer: SharedWriter,
    level: Level,
    format: LogFormat,
    timestamp: TimestampPolicy,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum LogFormat {
    Text,
    Json,
}

#[derive(Clone, Debug, Eq, PartialEq)]
enum TimestampPolicy {
    Current,
    Fixed(String),
}

/// Structured values supported by Go `slog` fixture vectors.
#[derive(Clone, Debug, PartialEq)]
pub enum LogValue {
    String(String),
    Bool(bool),
    I64(i64),
    U64(u64),
    F64(f64),
    Json(serde_json::Value),
    Group(Vec<LogAttr>),
}

/// A structured key/value attribute.
#[derive(Clone, Debug, PartialEq)]
pub struct LogAttr {
    pub key: String,
    pub value: LogValue,
}

impl LogAttr {
    pub fn new(key: impl Into<String>, value: LogValue) -> Self {
        Self {
            key: key.into(),
            value,
        }
    }

    pub fn string(key: impl Into<String>, value: impl Into<String>) -> Self {
        Self::new(key, LogValue::String(value.into()))
    }

    pub fn bool(key: impl Into<String>, value: bool) -> Self {
        Self::new(key, LogValue::Bool(value))
    }

    pub fn i64(key: impl Into<String>, value: i64) -> Self {
        Self::new(key, LogValue::I64(value))
    }
}

impl LogFormat {
    pub fn parse(value: &str) -> Self {
        if value.eq_ignore_ascii_case("json") {
            Self::Json
        } else {
            Self::Text
        }
    }
}

impl Logger {
    pub fn new<W>(writer: W, level: Level, format: impl AsRef<str>) -> Self
    where
        W: Write + Send + 'static,
    {
        Self::with_timestamp(writer, level, format, TimestampPolicy::Current)
    }

    /// Construct a logger with a fixed RFC3339Nano timestamp for oracle tests.
    pub fn new_fixed_time<W>(
        writer: W,
        level: Level,
        format: impl AsRef<str>,
        timestamp: impl Into<String>,
    ) -> Self
    where
        W: Write + Send + 'static,
    {
        Self::with_timestamp(
            writer,
            level,
            format,
            TimestampPolicy::Fixed(timestamp.into()),
        )
    }

    fn with_timestamp<W>(
        writer: W,
        level: Level,
        format: impl AsRef<str>,
        timestamp: TimestampPolicy,
    ) -> Self
    where
        W: Write + Send + 'static,
    {
        Self {
            writer: Arc::new(Mutex::new(Box::new(writer))),
            level,
            format: LogFormat::parse(format.as_ref()),
            timestamp,
        }
    }

    pub fn level(&self) -> Level {
        self.level
    }

    pub fn format(&self) -> LogFormat {
        self.format
    }

    pub fn enabled(&self, level: Level) -> bool {
        rank(level) >= rank(self.level)
    }

    pub fn log(&self, level: Level, message: impl AsRef<str>) -> io::Result<()> {
        self.log_attrs(level, message, &[])
    }

    pub fn log_attrs(
        &self,
        level: Level,
        message: impl AsRef<str>,
        attrs: &[LogAttr],
    ) -> io::Result<()> {
        if !self.enabled(level) {
            return Ok(());
        }
        let timestamp = match &self.timestamp {
            TimestampPolicy::Current => timestamp_now(self.format),
            TimestampPolicy::Fixed(value) => value.clone(),
        };
        self.write_record(&timestamp, level, message.as_ref(), attrs)
    }

    /// Emit a record with an explicit timestamp; intended for deterministic
    /// vectors, not as a replacement for the production clock policy.
    pub fn log_at(
        &self,
        timestamp: &str,
        level: Level,
        message: impl AsRef<str>,
        attrs: &[LogAttr],
    ) -> io::Result<()> {
        if !self.enabled(level) {
            return Ok(());
        }
        self.write_record(timestamp, level, message.as_ref(), attrs)
    }

    fn write_record(
        &self,
        timestamp: &str,
        level: Level,
        message: &str,
        attrs: &[LogAttr],
    ) -> io::Result<()> {
        let mut writer = self.writer.lock().expect("logger writer mutex poisoned");
        match self.format {
            LogFormat::Text => {
                write!(
                    writer,
                    "time={} level={} msg={}",
                    timestamp,
                    level_name(level),
                    text_value(&LogValue::String(message.to_string()))
                )?;
                for attr in attrs {
                    write_text_attr(&mut *writer, "", attr)?;
                }
                writeln!(writer)
            }
            LogFormat::Json => {
                write!(
                    writer,
                    "{{\"time\":{},\"level\":{},\"msg\":{}",
                    quote(timestamp),
                    quote(level_name(level)),
                    quote(message)
                )?;
                for attr in attrs {
                    write_json_attr(&mut *writer, "", attr)?;
                }
                writeln!(writer, "}}")
            }
        }
    }

    pub fn debug(&self, message: impl AsRef<str>) -> io::Result<()> {
        self.log(Level::DEBUG, message)
    }
    pub fn info(&self, message: impl AsRef<str>) -> io::Result<()> {
        self.log(Level::INFO, message)
    }
    pub fn warn(&self, message: impl AsRef<str>) -> io::Result<()> {
        self.log(Level::WARN, message)
    }
    pub fn error(&self, message: impl AsRef<str>) -> io::Result<()> {
        self.log(Level::ERROR, message)
    }
}

fn write_text_attr(writer: &mut dyn Write, prefix: &str, attr: &LogAttr) -> io::Result<()> {
    let key = if prefix.is_empty() {
        attr.key.clone()
    } else {
        format!("{prefix}.{}", attr.key)
    };
    match &attr.value {
        LogValue::Group(children) => {
            for child in children {
                write_text_attr(writer, &key, child)?;
            }
            Ok(())
        }
        value => write!(writer, " {}={}", text_string(&key), text_value(value)),
    }
}

fn write_json_attr(writer: &mut dyn Write, prefix: &str, attr: &LogAttr) -> io::Result<()> {
    let key = if prefix.is_empty() {
        attr.key.clone()
    } else {
        format!("{prefix}.{}", attr.key)
    };
    write!(writer, ",{}:", quote(&key))?;
    write_json_value(writer, &attr.value)
}

fn write_json_value(writer: &mut dyn Write, value: &LogValue) -> io::Result<()> {
    match value {
        LogValue::String(value) => write!(writer, "{}", quote(value)),
        LogValue::Bool(value) => write!(writer, "{value}"),
        LogValue::I64(value) => write!(writer, "{value}"),
        LogValue::U64(value) => write!(writer, "{value}"),
        LogValue::F64(value) => write!(
            writer,
            "{}",
            serde_json::to_string(value).unwrap_or_else(|_| "null".into())
        ),
        LogValue::Json(value) => {
            let encoded = serde_json::to_string(value).expect("JSON values serialize");
            writer.write_all(escape_json_separators(encoded).as_bytes())
        }
        LogValue::Group(children) => {
            write!(writer, "{{")?;
            for (index, child) in children.iter().enumerate() {
                if index > 0 {
                    write!(writer, ",")?;
                }
                write!(writer, "{}:", quote(&child.key))?;
                write_json_value(writer, &child.value)?;
            }
            write!(writer, "}}")
        }
    }
}

fn text_value(value: &LogValue) -> String {
    match value {
        LogValue::String(value) => text_string(value),
        LogValue::Bool(value) => value.to_string(),
        LogValue::I64(value) => value.to_string(),
        LogValue::U64(value) => value.to_string(),
        LogValue::F64(value) => value.to_string(),
        LogValue::Json(value) => value.to_string(),
        LogValue::Group(_) => unreachable!("groups are flattened before formatting"),
    }
}

fn text_string(value: &str) -> String {
    if !value.is_empty()
        && value.chars().all(|character| {
            !character.is_control()
                && !character.is_whitespace()
                && !matches!(character, '"' | '\\' | '=')
        })
    {
        value.to_string()
    } else {
        go_text_quote(value)
    }
}

fn go_text_quote(value: &str) -> String {
    let mut output = String::from("\"");
    for character in value.chars() {
        match character {
            '\u{7}' => output.push_str("\\a"),
            '\u{8}' => output.push_str("\\b"),
            '\u{c}' => output.push_str("\\f"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            '\u{b}' => output.push_str("\\v"),
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            character if character <= '\u{1f}' || character == '\u{7f}' => {
                output.push_str(&format!("\\x{:02x}", character as u32));
            }
            character => output.push(character),
        }
    }
    output.push('"');
    output
}

fn quote(value: &str) -> String {
    escape_json_separators(serde_json::to_string(value).expect("strings are valid JSON"))
}

fn escape_json_separators(value: String) -> String {
    value
        .replace('\u{2028}', "\\u2028")
        .replace('\u{2029}', "\\u2029")
}

fn level_name(level: Level) -> &'static str {
    match level {
        Level::ERROR => "ERROR",
        Level::WARN => "WARN",
        Level::INFO => "INFO",
        Level::DEBUG => "DEBUG",
        Level::TRACE => "TRACE",
    }
}

fn rank(level: Level) -> u8 {
    match level {
        Level::ERROR => 4,
        Level::WARN => 3,
        Level::INFO => 2,
        Level::DEBUG => 1,
        Level::TRACE => 0,
    }
}

/// Parse Go `slog` level names. Unknown and empty values default to WARN.
pub fn parse_level(value: &str) -> Level {
    match value.trim().to_ascii_lowercase().as_str() {
        "debug" => Level::DEBUG,
        "info" => Level::INFO,
        "error" => Level::ERROR,
        "warn" | "warning" => Level::WARN,
        _ => Level::WARN,
    }
}

pub fn new_from_env(app_name: &str) -> Logger {
    let prefix = app_name.to_ascii_uppercase();
    let level = parse_level(&getenv_nonempty(&format!("{prefix}_LOG_LEVEL")));
    let format = getenv_nonempty(&format!("{prefix}_LOG_FORMAT"));
    Logger::new(
        io::stderr(),
        level,
        if format.is_empty() { "text" } else { &format },
    )
}

fn getenv_nonempty(name: &str) -> String {
    env::var(name)
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_default()
}

fn timestamp_now(format: LogFormat) -> String {
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let nanos = match format {
        LogFormat::Text => now.subsec_millis() * 1_000_000,
        LogFormat::Json => now.subsec_nanos(),
    };
    format_timestamp(now.as_secs() as i64, nanos)
}

fn format_timestamp(seconds: i64, nanos: u32) -> String {
    let days = seconds.div_euclid(86_400);
    let day_seconds = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = day_seconds / 3_600;
    let minute = day_seconds % 3_600 / 60;
    let second = day_seconds % 60;
    let mut output = format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}");
    if nanos != 0 {
        let mut fraction = format!("{nanos:09}");
        while fraction.ends_with('0') {
            fraction.pop();
        }
        output.push('.');
        output.push_str(&fraction);
    }
    output.push('Z');
    output
}

// Howard Hinnant's proleptic-Gregorian civil date conversion.
fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let z = days + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    (y + if month <= 2 { 1 } else { 0 }, month, day)
}

static DEFAULT: OnceLock<Mutex<Option<Logger>>> = OnceLock::new();
fn default_slot() -> &'static Mutex<Option<Logger>> {
    DEFAULT.get_or_init(|| Mutex::new(None))
}

pub fn init_default(app_name: impl Into<String>) {
    let app_name = app_name.into();
    let mut slot = default_slot()
        .lock()
        .expect("default logger mutex poisoned");
    *slot = Some(new_from_env(if app_name.is_empty() {
        FALLBACK_APP
    } else {
        &app_name
    }));
}

pub fn default_logger() -> Logger {
    let mut slot = default_slot()
        .lock()
        .expect("default logger mutex poisoned");
    slot.get_or_insert_with(|| new_from_env(FALLBACK_APP))
        .clone()
}

/// Temporarily replace the process default logger. The previous value is restored on drop.
pub struct LoggerReplacement(Option<Logger>);
pub fn replace_logger(logger: Option<Logger>) -> LoggerReplacement {
    let mut slot = default_slot()
        .lock()
        .expect("default logger mutex poisoned");
    let previous = slot.take();
    *slot = logger;
    LoggerReplacement(previous)
}
impl Drop for LoggerReplacement {
    fn drop(&mut self) {
        let mut slot = default_slot()
            .lock()
            .expect("default logger mutex poisoned");
        *slot = self.0.take();
    }
}
