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

    pub(crate) fn http(status: u16, body: &[u8], retry_after: &str) -> Self {
        let decoded = String::from_utf8_lossy(body);
        let code = match status {
            401 | 403 => ErrorCode::AuthFailure,
            429 => ErrorCode::RateLimited,
            404 => ErrorCode::ModelNotFound,
            400 if overflow(&decoded) => ErrorCode::ContextOverflow,
            _ => ErrorCode::ProviderError,
        };
        let body = truncate_body_bytes(body);
        Self {
            code,
            status_code: status,
            body,
            retry_after: retry_after.to_owned(),
            detail: String::new(),
        }
    }
}

fn truncate_body_bytes(body: &[u8]) -> String {
    let mut start = 0;
    let mut end = 0;
    let mut pos = 0;
    while pos < body.len() {
        let remaining = &body[pos..];
        let window = &remaining[..remaining.len().min(4)];
        let (character, width) = match std::str::from_utf8(window) {
            Ok(valid) => {
                let character = valid.chars().next().expect("nonempty suffix");
                (character, character.len_utf8())
            }
            Err(error) if error.valid_up_to() > 0 => {
                let valid = std::str::from_utf8(&window[..error.valid_up_to()])
                    .expect("valid UTF-8 prefix");
                let character = valid.chars().next().expect("nonempty valid prefix");
                (character, character.len_utf8())
            }
            Err(_) => ('\u{fffd}', 1),
        };
        if !character.is_whitespace() {
            if end == 0 {
                start = pos;
            }
            end = pos + width;
        }
        pos += width;
    }
    let trimmed = &body[start..end];
    String::from_utf8_lossy(&trimmed[..trimmed.len().min(512)]).into_owned()
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

#[cfg(test)]
mod tests {
    use super::Error;

    #[test]
    fn provider_error_truncates_raw_bytes_before_utf8_decode() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
        ))
        .unwrap();
        let mut raw = vec![0xff; 171];
        raw.extend(std::iter::repeat_n(b'x', 500));
        let error = Error::http(400, &raw, "");
        assert_eq!(error.body, fixture["invalid_utf8_error_body"]);
    }
}
