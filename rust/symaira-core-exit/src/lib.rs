#![deny(unsafe_code)]

//! Standard Symaira CLI exit codes and structured errors.

use std::error::Error;
use std::fmt;

/// Stable process exit status categories.
#[repr(u8)]
#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub enum ExitCode {
    Ok = 0,
    Generic = 1,
    NoInput = 2,
    NoAuth = 3,
    Forbidden = 4,
    NotFound = 5,
    Conflict = 6,
    Software = 7,
    Data = 8,
    Config = 9,
    Interrupted = 10,
}

impl ExitCode {
    pub const EXIT_OK: Self = Self::Ok;
    pub const EXIT_GENERIC: Self = Self::Generic;
    pub const EXIT_NO_INPUT: Self = Self::NoInput;
    pub const EXIT_NO_AUTH: Self = Self::NoAuth;
    pub const EXIT_FORBIDDEN: Self = Self::Forbidden;
    pub const EXIT_NOT_FOUND: Self = Self::NotFound;
    pub const EXIT_CONFLICT: Self = Self::Conflict;
    pub const EXIT_SOFTWARE: Self = Self::Software;
    pub const EXIT_DATA: Self = Self::Data;
    pub const EXIT_CONFIG: Self = Self::Config;
    pub const EXIT_INTERRUPTED: Self = Self::Interrupted;

    pub const fn as_u8(self) -> u8 {
        self as u8
    }
}

impl From<ExitCode> for u8 {
    fn from(value: ExitCode) -> Self {
        value as u8
    }
}

impl TryFrom<u8> for ExitCode {
    type Error = u8;

    fn try_from(value: u8) -> Result<Self, Self::Error> {
        Ok(match value {
            0 => Self::Ok,
            1 => Self::Generic,
            2 => Self::NoInput,
            3 => Self::NoAuth,
            4 => Self::Forbidden,
            5 => Self::NotFound,
            6 => Self::Conflict,
            7 => Self::Software,
            8 => Self::Data,
            9 => Self::Config,
            10 => Self::Interrupted,
            other => return Err(other),
        })
    }
}

/// Machine-readable error classification.
#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
pub enum ErrorKind {
    NotFound,
    Auth,
    Permission,
    Validation,
    Config,
    Conflict,
    Internal,
    Unavailable,
}

impl ErrorKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::NotFound => "not_found",
            Self::Auth => "auth",
            Self::Permission => "permission",
            Self::Validation => "validation",
            Self::Config => "config",
            Self::Conflict => "conflict",
            Self::Internal => "internal",
            Self::Unavailable => "unavailable",
        }
    }
}

impl fmt::Display for ErrorKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// A user-facing error carrying stable exit and classification metadata.
#[derive(Debug)]
pub struct CliError {
    pub code: ExitCode,
    pub kind: ErrorKind,
    pub message: String,
    pub cause: Option<Box<dyn Error + Send + Sync + 'static>>,
    pub hint: Option<String>,
}

impl CliError {
    pub fn new(code: ExitCode, kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            code,
            kind,
            message: message.into(),
            cause: None,
            hint: None,
        }
    }

    pub fn with_hint(mut self, hint: impl Into<String>) -> Self {
        self.hint = Some(hint.into());
        self
    }

    pub fn with_cause<E>(mut self, cause: E) -> Self
    where
        E: Error + Send + Sync + 'static,
    {
        self.cause = Some(Box::new(cause));
        self
    }
}

impl fmt::Display for CliError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)?;
        if let Some(cause) = &self.cause {
            write!(f, ": {cause}")?;
        }
        Ok(())
    }
}

impl Error for CliError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        self.cause
            .as_deref()
            .map(|error| error as &(dyn Error + 'static))
    }
}

pub type CLIError = CliError;

pub fn wrap<E>(cause: E, code: ExitCode, kind: ErrorKind, message: impl Into<String>) -> CliError
where
    E: Error + Send + Sync + 'static,
{
    CliError::new(code, kind, message).with_cause(cause)
}

pub fn wrapf<E>(cause: E, code: ExitCode, kind: ErrorKind, message: String) -> CliError
where
    E: Error + Send + Sync + 'static,
{
    wrap(cause, code, kind, message)
}

pub fn exit_code_from_error(error: Option<&(dyn Error + 'static)>) -> ExitCode {
    let Some(error) = error else {
        return ExitCode::Ok;
    };
    if let Some(cli) = error.downcast_ref::<CliError>() {
        return cli.code;
    }
    let mut source = error.source();
    while let Some(current) = source {
        if let Some(cli) = current.downcast_ref::<CliError>() {
            return cli.code;
        }
        source = current.source();
    }
    ExitCode::Generic
}

pub fn format_cli_error(error: Option<&(dyn Error + 'static)>) -> String {
    let Some(error) = error else {
        return String::new();
    };
    let fallback = error.to_string();
    // Go's errors.As stops at the first CLIError in the unwrap chain. If that
    // error has no hint, a deeper CLIError's hint is deliberately not used.
    let mut current = Some(error);
    while let Some(candidate) = current {
        if let Some(cli) = candidate.downcast_ref::<CliError>() {
            let output = cli.to_string();
            if let Some(hint) = cli.hint.as_deref().filter(|hint| !hint.is_empty()) {
                return format!("{output}\nHint: {hint}");
            }
            return output;
        }
        current = candidate.source();
    }
    fallback
}
