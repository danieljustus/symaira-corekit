use serde::Serialize;
use std::fmt;
use symaira_core_exit::ExitCode;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorCode {
    AuthFailure,
    RateLimited,
    ContextOverflow,
    ModelNotFound,
    TransportError,
    ProviderError,
}

impl ErrorCode {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::AuthFailure => "auth_failure",
            Self::RateLimited => "rate_limited",
            Self::ContextOverflow => "context_overflow",
            Self::ModelNotFound => "model_not_found",
            Self::TransportError => "transport_error",
            Self::ProviderError => "provider_error",
        }
    }

    pub const fn retryable(self) -> bool {
        matches!(self, Self::RateLimited | Self::TransportError)
    }

    pub const fn exit_code(self) -> ExitCode {
        match self {
            Self::AuthFailure => ExitCode::NoAuth,
            Self::RateLimited => ExitCode::Conflict,
            Self::ContextOverflow => ExitCode::Data,
            Self::ModelNotFound => ExitCode::NotFound,
            Self::TransportError | Self::ProviderError => ExitCode::Generic,
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Error {
    pub code: ErrorCode,
    pub status_code: u16,
    pub body: String,
    pub retry_after: String,
    pub detail: String,
}

impl Error {
    pub(crate) fn local(code: ErrorCode, detail: impl Into<String>) -> Self {
        Self {
            code,
            status_code: 0,
            body: String::new(),
            retry_after: String::new(),
            detail: detail.into(),
        }
    }

    pub(crate) fn transport(detail: impl Into<String>) -> Self {
        Self::local(ErrorCode::TransportError, detail)
    }

    pub fn retryable(&self) -> bool {
        self.code.retryable()
    }

    pub fn retry_after_seconds(&self) -> Option<i64> {
        if self.retry_after.is_empty() {
            return None;
        }
        self.retry_after
            .parse::<i64>()
            .ok()
            .filter(|seconds| *seconds >= 0)
    }

    pub fn exit_code(&self) -> ExitCode {
        self.code.exit_code()
    }

    pub(crate) fn http(status: u16, body: &str, retry_after: &str) -> Self {
        let code = match status {
            401 | 403 => ErrorCode::AuthFailure,
            429 => ErrorCode::RateLimited,
            404 => ErrorCode::ModelNotFound,
            400 if overflow(body) => ErrorCode::ContextOverflow,
            _ => ErrorCode::ProviderError,
        };
        let body = body.trim();
        let body = if body.len() <= 512 {
            body.to_owned()
        } else {
            String::from_utf8_lossy(&body.as_bytes()[..512]).into_owned()
        };
        Self {
            code,
            status_code: status,
            body,
            retry_after: retry_after.to_owned(),
            detail: String::new(),
        }
    }
}

fn overflow(body: &str) -> bool {
    let body = body.to_ascii_lowercase();
    [
        "context_length_exceeded",
        "maximum context length",
        "context window",
        "too many tokens",
        "input length exceeds",
    ]
    .iter()
    .any(|marker| body.contains(marker))
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.status_code == 0
            && self.body.is_empty()
            && self.detail.starts_with("llmkit: auth_failure:")
        {
            return f.write_str(&self.detail);
        }
        let detail = self.detail.strip_prefix("llmkit: ").unwrap_or(&self.detail);
        write!(f, "llmkit: {}", self.code.as_str())?;
        if self.status_code != 0 {
            write!(f, " (status {})", self.status_code)?;
        }
        if !self.body.is_empty() {
            write!(f, ": {}", self.body)?;
        } else if !detail.is_empty() {
            write!(f, ": {detail}")?;
        }
        Ok(())
    }
}

impl std::error::Error for Error {}
