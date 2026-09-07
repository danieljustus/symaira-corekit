use std::io::Write;
use std::sync::{Arc, Mutex};
use symaira_core_log::{
    LogAttr, LogFormat, LogValue, Logger, default_logger, init_default, new_from_env, parse_level,
    replace_logger,
};
use tracing::Level;

#[derive(Clone, Default)]
struct Buffer(Arc<Mutex<Vec<u8>>>);
impl Write for Buffer {
    fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
        self.0.lock().unwrap().extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}
fn output(buffer: &Buffer) -> String {
    String::from_utf8(buffer.0.lock().unwrap().clone()).unwrap()
}
fn fixture(id: &str) -> serde_json::Value {
    symaira_contract_fixtures::json(symaira_contract_fixtures::foundation(id))
}

#[test]
fn log_001_level_parser_matches_go_fixture() {
    let levels = &fixture("LOG-001")["levels"];
    for input in ["debug", "info", "warn", "warning", "error", "bogus", ""] {
        let expected = levels[input].as_str().unwrap();
        assert_eq!(
            parse_level(input).to_string().to_ascii_uppercase(),
            expected
        );
    }
}

#[test]
fn log_002_text_logging_preserves_time_fields_escaping_and_filtering() {
    let buffer = Buffer::default();
    let logger = Logger::new_fixed_time(
        buffer.clone(),
        Level::INFO,
        "text",
        "2024-01-02T03:04:05.678Z",
    );
    logger.debug("hidden").unwrap();
    logger
        .log_attrs(
            Level::INFO,
            "hello",
            &[
                LogAttr::string("path", "a\nb"),
                LogAttr::new(
                    "request",
                    LogValue::Group(vec![LogAttr::string("id", "x"), LogAttr::bool("ok", true)]),
                ),
            ],
        )
        .unwrap();
    assert_eq!(
        output(&buffer),
        fixture("LOG-002")["output"].as_str().unwrap()
    );
    let control_buffer = Buffer::default();
    let control = Logger::new_fixed_time(
        control_buffer.clone(),
        Level::DEBUG,
        "text",
        "2024-01-02T03:04:05.678Z",
    );
    control
        .log_attrs(
            Level::INFO,
            "nul\0message",
            &[
                LogAttr::string("value", "nul\0value"),
                LogAttr::string("bad key=", "quoted"),
            ],
        )
        .unwrap();
    assert_eq!(
        output(&control_buffer),
        fixture("LOG-002")["control_output"].as_str().unwrap()
    );
    let trace_buffer = Buffer::default();
    let info_logger = Logger::new_fixed_time(
        trace_buffer.clone(),
        Level::INFO,
        "text",
        "2024-01-02T03:04:05.678Z",
    );
    info_logger.log(Level::TRACE, "hidden trace").unwrap();
    assert!(output(&trace_buffer).is_empty());
    let trace_logger = Logger::new_fixed_time(
        trace_buffer.clone(),
        Level::TRACE,
        "text",
        "2024-01-02T03:04:05.678Z",
    );
    trace_logger.log(Level::TRACE, "visible").unwrap();
    assert!(output(&trace_buffer).contains("level=TRACE msg=visible"));
}

#[test]
fn log_003_json_logging_preserves_structured_fields() {
    let buffer = Buffer::default();
    let logger = Logger::new_fixed_time(
        buffer.clone(),
        Level::DEBUG,
        "json",
        "2024-01-02T03:04:05.678901234Z",
    );
    assert_eq!(logger.format(), LogFormat::Json);
    logger
        .log_attrs(
            Level::DEBUG,
            "quoted \"message\"",
            &[
                LogAttr::i64("count", 3),
                LogAttr::string("newline", "a\nb"),
                LogAttr::new("request", LogValue::Group(vec![LogAttr::string("id", "x")])),
            ],
        )
        .unwrap();
    assert_eq!(
        output(&buffer),
        fixture("LOG-003")["output"].as_str().unwrap()
    );
    let unicode_buffer = Buffer::default();
    let unicode_logger = Logger::new_fixed_time(
        unicode_buffer.clone(),
        Level::INFO,
        "json",
        "2024-01-02T03:04:05.678901234Z",
    );
    unicode_logger
        .log_attrs(
            Level::INFO,
            "line\u{2028}paragraph\u{2029}",
            &[
                LogAttr::string("key\u{2028}", "value\u{2029}"),
                LogAttr::new(
                    "nested",
                    LogValue::Json(serde_json::json!({"value": "nested\u{2028}"})),
                ),
            ],
        )
        .unwrap();
    assert_eq!(
        output(&unicode_buffer),
        fixture("LOG-003")["unicode_output"].as_str().unwrap()
    );
}

#[test]
fn log_004_default_replacement_and_env_format_remain_scoped() {
    let expected = fixture("LOG-004");
    let buffer = Buffer::default();
    let custom =
        Logger::new_fixed_time(buffer.clone(), Level::INFO, "text", "2024-01-02T03:04:05Z");
    let replacement = replace_logger(Some(custom));
    default_logger().info("replaced").unwrap();
    assert!(output(&buffer).contains("replaced"));
    drop(replacement);
    init_default("");
    assert_eq!(new_from_env("missing-app").format(), LogFormat::Text);
    assert_eq!(expected["format"].as_str().unwrap(), "json");
}
