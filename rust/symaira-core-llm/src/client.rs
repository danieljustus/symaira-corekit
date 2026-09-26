use crate::error::{Error, ErrorCode, Result};
use crate::provider::{AuthScheme, Descriptor, WireDialect};
use serde::Serialize;
use std::net::IpAddr;
use std::time::Duration;
use ureq::{Agent, http};

pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(120);
const MAX_ERROR_BODY: usize = 8 * 1024;

pub struct ClientBuilder {
    descriptor: Descriptor,
    credential_ref: String,
    base_url: Option<String>,
    dialect: Option<WireDialect>,
    timeout: Duration,
    api_key: Option<String>,
}

impl ClientBuilder {
    pub fn new(descriptor: Descriptor, credential_ref: impl Into<String>) -> Self {
        Self {
            descriptor,
            credential_ref: credential_ref.into(),
            base_url: None,
            dialect: None,
            timeout: DEFAULT_TIMEOUT,
            api_key: None,
        }
    }

    pub fn base_url(mut self, value: impl Into<String>) -> Self {
        self.base_url = Some(value.into());
        self
    }
    pub fn dialect(mut self, value: WireDialect) -> Self {
        self.dialect = Some(value);
        self
    }
    pub fn timeout(mut self, value: Duration) -> Self {
        self.timeout = value;
        self
    }
    pub fn api_key(mut self, value: impl Into<String>) -> Self {
        self.api_key = Some(value.into());
        self
    }

    pub fn build(self) -> Result<Client> {
        self.descriptor
            .validate()
            .map_err(|e| Error::local(ErrorCode::ProviderError, e))?;
        let base_url = self
            .base_url
            .unwrap_or_else(|| self.descriptor.base_url.clone());
        if base_url != self.descriptor.base_url
            && !self.descriptor.base_url_overridable
            && !self.descriptor.base_url_required_override
        {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not allow base URL overrides",
                    self.descriptor.id
                ),
            ));
        }
        if base_url.is_empty() && self.descriptor.base_url_required_override {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} requires a base URL override (WithBaseURL)",
                    self.descriptor.id
                ),
            ));
        }
        validate_base_url(&base_url, &self.descriptor)?;
        let dialect = self.dialect.unwrap_or(self.descriptor.dialect);
        if dialect != self.descriptor.dialect && !self.descriptor.dialect_configurable {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not allow dialect overrides",
                    self.descriptor.id
                ),
            ));
        }
        let api_key = match self.descriptor.auth_scheme {
            AuthScheme::None => String::new(),
            _ => match self.api_key {
                Some(value) => value,
                None => resolve_credential(
                    &self.credential_ref,
                    &self.descriptor.credential_env_default,
                )?,
            },
        };
        let agent = Agent::config_builder()
            .http_status_as_error(false)
            .max_redirects(0)
            .timeout_global(Some(self.timeout))
            .build()
            .into();
        Ok(Client {
            descriptor: self.descriptor,
            base_url: base_url.trim_end_matches('/').to_owned(),
            dialect,
            api_key,
            agent,
        })
    }
}

pub struct Client {
    descriptor: Descriptor,
    base_url: String,
    pub(crate) dialect: WireDialect,
    api_key: String,
    agent: Agent,
}

impl Client {
    pub fn descriptor(&self) -> &Descriptor {
        &self.descriptor
    }
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub(crate) fn request<T: Serialize>(
        &self,
        method: &str,
        path: &str,
        body: Option<&T>,
    ) -> Result<ureq::http::Response<ureq::Body>> {
        let url = format!("{}/{}", self.base_url, path.trim_start_matches('/'));
        let json = body
            .map(serde_json::to_string)
            .transpose()
            .map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: encode request: {e}"),
                )
            })?
            .unwrap_or_default();
        let mut request = http::Request::builder()
            .method(method)
            .uri(&url)
            .body(json)
            .map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: build request: {e}"),
                )
            })?;
        request.headers_mut().insert(
            http::header::ACCEPT,
            http::HeaderValue::from_static("application/json"),
        );
        if body.is_some() {
            request.headers_mut().insert(
                http::header::CONTENT_TYPE,
                http::HeaderValue::from_static("application/json"),
            );
        }
        let auth = match self.descriptor.auth_scheme {
            AuthScheme::Bearer => Some(("Authorization", format!("Bearer {}", self.api_key))),
            AuthScheme::Header => Some((
                if self.descriptor.auth_header.is_empty() {
                    "Authorization"
                } else {
                    &self.descriptor.auth_header
                },
                self.api_key.clone(),
            )),
            AuthScheme::None => None,
        };
        if let Some((name, value)) = auth {
            let name = http::header::HeaderName::from_bytes(name.as_bytes()).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: invalid auth header: {e}"),
                )
            })?;
            let value = http::header::HeaderValue::from_str(&value).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: invalid auth value: {e}"),
                )
            })?;
            request.headers_mut().insert(name, value);
        }
        for (name, value) in &self.descriptor.extra_headers {
            let name = http::header::HeaderName::from_bytes(name.as_bytes()).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: invalid provider header: {e}"),
                )
            })?;
            let value = http::header::HeaderValue::from_str(value).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: invalid provider header value: {e}"),
                )
            })?;
            request.headers_mut().insert(name, value);
        }
        let mut response = self
            .agent
            .run(request)
            .map_err(|e| Error::transport(e.to_string()))?;
        let status = response.status().as_u16();
        if status >= 300 {
            let retry_after = response
                .headers()
                .get("retry-after")
                .and_then(|v| v.to_str().ok())
                .unwrap_or_default()
                .to_owned();
            let raw = response
                .body_mut()
                .with_config()
                .limit(MAX_ERROR_BODY as u64)
                .read_to_vec()
                .unwrap_or_default();
            let excerpt = String::from_utf8_lossy(&raw);
            return Err(Error::http(status, &excerpt, &retry_after));
        }
        Ok(response)
    }
}

fn resolve_credential(reference: &str, env_default: &str) -> Result<String> {
    let target = if reference.is_empty() {
        env_default
    } else {
        reference
    };
    if target.starts_with("keychain://") {
        return Err(Error::local(
            ErrorCode::AuthFailure,
            "llmkit: auth_failure: keychain:// references are resolved by the Swift half (SymairaProviderKit), not by llmkit",
        ));
    }
    if target.is_empty() {
        return Err(Error::local(
            ErrorCode::AuthFailure,
            "llmkit: auth_failure: no credential reference or default provided",
        ));
    }
    let label = if reference.is_empty() {
        "<default>"
    } else {
        reference
    };
    symaira_core_secretref::resolve(reference, env_default).map_err(|error| {
        let detail = match error {
            symaira_core_secretref::ResolveError::EnvironmentUnset { name } => {
                format!("environment variable {name} is not set (reference {label})")
            }
            other => format!("resolve {label}: {other}"),
        };
        Error::local(
            ErrorCode::AuthFailure,
            format!("llmkit: auth_failure: {detail}"),
        )
    })
}

fn validate_base_url(base_url: &str, descriptor: &Descriptor) -> Result<()> {
    if descriptor.auth_scheme == AuthScheme::None {
        return Ok(());
    }
    let Some((scheme, authority)) = base_url.split_once("://") else {
        return Err(Error::local(
            ErrorCode::AuthFailure,
            format!(
                "provider {:?} requires an HTTPS base URL for credentialed requests",
                descriptor.id
            ),
        ));
    };
    let host = authority
        .split('/')
        .next()
        .unwrap_or_default()
        .split('@')
        .next_back()
        .unwrap_or_default();
    if host.is_empty() {
        return Err(Error::local(
            ErrorCode::AuthFailure,
            format!(
                "provider {:?} requires an HTTPS base URL for credentialed requests",
                descriptor.id
            ),
        ));
    }
    if scheme.eq_ignore_ascii_case("https") || is_loopback(host) {
        return Ok(());
    }
    Err(Error::local(
        ErrorCode::AuthFailure,
        format!(
            "provider {:?} requires an HTTPS base URL for credentialed requests outside loopback hosts",
            descriptor.id
        ),
    ))
}

fn is_loopback(authority: &str) -> bool {
    if authority.eq_ignore_ascii_case("localhost")
        || authority.to_ascii_lowercase().starts_with("localhost:")
    {
        return true;
    }
    let host = if let Some(host) = authority.strip_prefix('[') {
        host.split(']').next().unwrap_or_default()
    } else {
        authority.split(':').next().unwrap_or_default()
    };
    host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
}

pub(crate) fn read_limited(
    response: &mut ureq::http::Response<ureq::Body>,
    limit: u64,
) -> Result<Vec<u8>> {
    response
        .body_mut()
        .with_config()
        .limit(limit)
        .read_to_vec()
        .map_err(|e| Error::transport(e.to_string()))
}
