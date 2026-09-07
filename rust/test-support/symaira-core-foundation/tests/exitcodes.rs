use std::error::Error;
use symaira_core_exit::{
    CliError, ErrorKind, ExitCode, exit_code_from_error, format_cli_error, wrap,
};

fn fixture(id: &str) -> serde_json::Value {
    symaira_contract_fixtures::json(symaira_contract_fixtures::foundation(id))
}

#[derive(Debug)]
struct ContextError(CliError);

impl std::fmt::Display for ContextError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(formatter, "context: {}", self.0)
    }
}

impl Error for ContextError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        Some(&self.0)
    }
}

#[test]
fn exit_001_codes_are_fixture_backed() {
    let expected = fixture("EXIT-001");
    for (name, code) in [
        ("ok", ExitCode::Ok),
        ("generic", ExitCode::Generic),
        ("no_input", ExitCode::NoInput),
        ("no_auth", ExitCode::NoAuth),
        ("forbidden", ExitCode::Forbidden),
        ("not_found", ExitCode::NotFound),
        ("conflict", ExitCode::Conflict),
        ("software", ExitCode::Software),
        ("data", ExitCode::Data),
        ("config", ExitCode::Config),
        ("interrupted", ExitCode::Interrupted),
    ] {
        assert_eq!(
            expected["codes"][name].as_u64().unwrap(),
            u64::from(code.as_u8())
        );
    }
}

#[test]
fn exit_002_error_chain_and_wrapping_match_go() {
    let cause = std::io::Error::other("underlying issue");
    let error = wrap(
        cause,
        ExitCode::Generic,
        ErrorKind::Internal,
        "operation failed",
    );
    let expected = fixture("EXIT-002");
    assert_eq!(error.to_string(), expected["error"].as_str().unwrap());
    assert_eq!(
        error.source().unwrap().to_string(),
        expected["cause"].as_str().unwrap()
    );
}

#[test]
fn exit_003_classifies_nil_plain_and_wrapped_errors() {
    let expected = fixture("EXIT-003");
    assert_eq!(
        exit_code_from_error(None).as_u8(),
        expected["nil"].as_u64().unwrap() as u8
    );
    let plain = std::io::Error::other("plain");
    assert_eq!(
        exit_code_from_error(Some(&plain)).as_u8(),
        expected["plain"].as_u64().unwrap() as u8
    );
    let typed = CliError::new(ExitCode::NotFound, ErrorKind::NotFound, "missing");
    assert_eq!(
        exit_code_from_error(Some(&typed)).as_u8(),
        expected["typed"].as_u64().unwrap() as u8
    );
    let outer = wrap(typed, ExitCode::Generic, ErrorKind::Internal, "read failed");
    assert_eq!(
        exit_code_from_error(Some(&outer)).as_u8(),
        expected["wrapped"].as_u64().unwrap() as u8
    );
}

#[test]
fn exit_004_format_discovers_nested_hint() {
    let expected = fixture("EXIT-004");
    let inner = CliError::new(ExitCode::NotFound, ErrorKind::NotFound, "entry missing")
        .with_hint("list entries");
    let outer = wrap(inner, ExitCode::Generic, ErrorKind::Internal, "read failed");
    assert_eq!(
        format_cli_error(Some(&outer)),
        expected["nested_hint"].as_str().unwrap()
    );
    assert_eq!(format_cli_error(None), expected["nil"].as_str().unwrap());
    let wrapped = ContextError(
        CliError::new(ExitCode::NotFound, ErrorKind::NotFound, "entry missing")
            .with_hint("list entries"),
    );
    assert_eq!(
        format_cli_error(Some(&wrapped)),
        expected["non_cli_wrapper"].as_str().unwrap()
    );
}
