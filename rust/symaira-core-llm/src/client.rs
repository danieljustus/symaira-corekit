use crate::error::{Error, ErrorCode, Result};
use crate::provider::{AuthScheme, Descriptor, WireDialect};
use serde::Serialize;
use std::future::Future;
use std::io::{self, Cursor, Read};
use std::net::IpAddr;
use std::sync::OnceLock;
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::thread::JoinHandle;
use std::time::Duration;
use tokio_util::sync::CancellationToken;
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
    agent: Option<Agent>,
    async_client: Option<reqwest::Client>,
    http_client: Option<reqwest::Client>,
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
            agent: None,
            async_client: None,
            http_client: None,
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
    /// Replaces the default HTTP agent with one configured by the caller.
    /// Its redirect, timeout, proxy, and TLS behavior is caller-controlled;
    /// `timeout` applies only when the default agent is used.
    pub fn agent(mut self, value: Agent) -> Self {
        self.agent = Some(value);
        self
    }
    /// Replaces the default transport for cancellable calls.
    /// Redirects, timeout, proxy, and TLS behavior are caller-controlled.
    pub fn async_client(mut self, value: reqwest::Client) -> Self {
        self.async_client = Some(value);
        self
    }
    /// Uses one HTTP client for both blocking and cancellable operations.
    ///
    /// Blocking operations drive this client's async response on a joined
    /// helper thread; cancellable operations use it directly and drop the
    /// request future when cancelled. This preserves caller transport
    /// configuration across both APIs.
    pub fn http_client(mut self, value: reqwest::Client) -> Self {
        self.http_client = Some(value);
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
        let api_key = match self.descriptor.auth_scheme {
            AuthScheme::None => String::new(),
            _ => match self.api_key.filter(|key| !key.is_empty()) {
                Some(value) => value,
                None => resolve_credential(
                    &self.credential_ref,
                    &self.descriptor.credential_env_default,
                )?,
            },
        };
        if self.http_client.is_some() && (self.agent.is_some() || self.async_client.is_some()) {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: http_client cannot be combined with agent or async_client",
            ));
        }
        let shared_http_client = self.http_client;
        let has_injected_agent = self.agent.is_some();
        let agent = self.agent.unwrap_or_else(|| {
            Agent::config_builder()
                .http_status_as_error(false)
                .max_redirects(0)
                .timeout_global((!self.timeout.is_zero()).then_some(self.timeout))
                .build()
                .into()
        });
        let cancellable_agent = match (shared_http_client.clone(), self.async_client) {
            (Some(client), _) => Some(OnceLock::from(Ok(client))),
            (None, Some(client)) => Some(OnceLock::from(Ok(client))),
            (None, None) if !has_injected_agent => Some(OnceLock::new()),
            (None, None) => None,
        };
        Ok(Client {
            descriptor: self.descriptor,
            base_url: base_url.trim_end_matches('/').to_owned(),
            dialect,
            api_key,
            agent,
            cancellable_agent,
            http_client: shared_http_client,
            timeout: self.timeout,
        })
    }
}

pub(crate) async fn cancel_on<T>(
    token: &CancellationToken,
    operation: impl Future<Output = Result<T>>,
) -> Result<T> {
    tokio::select! {
        biased;
        _ = token.cancelled() => Err(Error::transport("llmkit: context canceled")),
        result = operation => result,
    }
}

pub struct Client {
    descriptor: Descriptor,
    base_url: String,
    pub(crate) dialect: WireDialect,
    api_key: String,
    agent: Agent,
    cancellable_agent: Option<OnceLock<std::result::Result<reqwest::Client, String>>>,
    http_client: Option<reqwest::Client>,
    timeout: Duration,
}

impl Client {
    pub fn descriptor(&self) -> &Descriptor {
        &self.descriptor
    }
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    pub(crate) async fn request_cancellable<T: Serialize>(
        &self,
        method: reqwest::Method,
        path: &str,
        body: Option<&T>,
    ) -> Result<reqwest::Response> {
        let Some(agent_cell) = &self.cancellable_agent else {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: cancellable calls cannot use an injected ureq Agent",
            ));
        };
        let agent = agent_cell.get_or_init(|| {
            let builder = reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .user_agent("Go-http-client/1.1");
            let builder = if self.timeout.is_zero() {
                builder
            } else {
                builder.timeout(self.timeout)
            };
            builder
                .build()
                .map_err(|error| error.without_url().to_string())
        });
        let agent = agent.as_ref().map_err(|detail| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: build cancellable HTTP client: {detail}"),
            )
        })?;
        let request = self.request_builder(agent, method, path, body)?;
        let mut response = request
            .send()
            .await
            .map_err(|error| Error::transport(error.without_url().to_string()))?;
        let status = response.status().as_u16();
        if status >= 300 {
            let retry_after = response
                .headers()
                .get(reqwest::header::RETRY_AFTER)
                .and_then(|value| value.to_str().ok())
                .unwrap_or_default()
                .to_owned();
            let mut raw = Vec::new();
            while raw.len() < MAX_ERROR_BODY {
                let chunk = response
                    .chunk()
                    .await
                    .map_err(|error| Error::transport(error.without_url().to_string()))?;
                let Some(chunk) = chunk else { break };
                let remaining = MAX_ERROR_BODY - raw.len();
                raw.extend_from_slice(&chunk[..chunk.len().min(remaining)]);
            }
            return Err(Error::http(status, &raw, &retry_after));
        }
        Ok(response)
    }

    fn request_builder<T: Serialize>(
        &self,
        client: &reqwest::Client,
        method: reqwest::Method,
        path: &str,
        body: Option<&T>,
    ) -> Result<reqwest::RequestBuilder> {
        let url = join_url_path(&self.base_url, path)?;
        let mut request = client
            .request(method, url)
            .header(reqwest::header::ACCEPT, "application/json")
            .header(reqwest::header::USER_AGENT, "Go-http-client/1.1");
        if let Some(body) = body {
            let json = serde_json::to_string(body).map_err(|error| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: encode request: {error}"),
                )
            })?;
            request = request
                .header(reqwest::header::CONTENT_TYPE, "application/json")
                .body(json);
        }
        match self.descriptor.auth_scheme {
            AuthScheme::Bearer => {
                let (name, value) = checked_header(
                    "Authorization",
                    &format!("Bearer {}", self.api_key),
                    "invalid auth header",
                    "invalid auth value",
                )?;
                request = request.header(name, value);
            }
            AuthScheme::Header => {
                let name = if self.descriptor.auth_header.is_empty() {
                    "Authorization"
                } else {
                    &self.descriptor.auth_header
                };
                let (name, value) = checked_header(
                    name,
                    &self.api_key,
                    "invalid auth header",
                    "invalid auth value",
                )?;
                request = request.header(name, value);
            }
            AuthScheme::None => {}
        }
        for (name, value) in &self.descriptor.extra_headers {
            let (name, value) = checked_header(
                name,
                value,
                "invalid provider header",
                "invalid provider header value",
            )?;
            request = request.header(name, value);
        }
        Ok(request)
    }

    pub(crate) fn request<T: Serialize>(
        &self,
        method: &str,
        path: &str,
        body: Option<&T>,
    ) -> Result<SyncResponse> {
        if let Some(client) = &self.http_client {
            return self.request_shared(client.clone(), method, path, body);
        }
        let url = join_url_path(&self.base_url, path)?;
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
            let (name, value) =
                checked_header(name, &value, "invalid auth header", "invalid auth value")?;
            request.headers_mut().insert(name, value);
        }
        for (name, value) in &self.descriptor.extra_headers {
            let (name, value) = checked_header(
                name,
                value,
                "invalid provider header",
                "invalid provider header value",
            )?;
            request.headers_mut().insert(name, value);
        }
        let mut response = self
            .agent
            .run(
                self.agent
                    .configure_request(request)
                    .http_status_as_error(false)
                    .build(),
            )
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
            return Err(Error::http(status, &raw, &retry_after));
        }
        Ok(SyncResponse::Ureq(response))
    }

    fn request_shared<T: Serialize>(
        &self,
        client: reqwest::Client,
        method: &str,
        path: &str,
        body: Option<&T>,
    ) -> Result<SyncResponse> {
        let method = reqwest::Method::from_bytes(method.as_bytes()).map_err(|error| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: build request: {error}"),
            )
        })?;
        let request = self
            .request_builder(&client, method, path, body)?
            .build()
            .map_err(|error| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: build request: {error}"),
                )
            })?;
        let cancellation = CancellationToken::new();
        let worker_token = cancellation.clone();
        let (started_tx, started_rx) = mpsc::sync_channel(1);
        let (chunks_tx, chunks_rx) = mpsc::sync_channel(1);
        let worker = std::thread::Builder::new()
            .name("llmkit-blocking-http".into())
            .spawn(move || run_shared_request(client, request, worker_token, started_tx, chunks_tx))
            .map_err(|error| Error::transport(format!("llmkit: start HTTP worker: {error}")))?;
        match started_rx.recv() {
            Ok(Ok(())) => {}
            Ok(Err(error)) => {
                cancellation.cancel();
                drop(chunks_rx);
                let _ = worker.join();
                return Err(error);
            }
            Err(_) => {
                cancellation.cancel();
                drop(chunks_rx);
                let _ = worker.join();
                return Err(Error::transport(
                    "llmkit: HTTP worker stopped before response",
                ));
            }
        }
        Ok(SyncResponse::Shared(SharedResponse {
            chunks: Some(chunks_rx),
            pending: Cursor::new(Vec::new()),
            cancellation,
            worker: Some(worker),
        }))
    }
}

pub(crate) enum SyncResponse {
    Ureq(ureq::http::Response<ureq::Body>),
    Shared(SharedResponse),
}

impl Read for SyncResponse {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        match self {
            Self::Ureq(response) => response.body_mut().as_reader().read(buffer),
            Self::Shared(response) => response.read(buffer),
        }
    }
}

pub(crate) struct SharedResponse {
    chunks: Option<Receiver<io::Result<Vec<u8>>>>,
    pending: Cursor<Vec<u8>>,
    cancellation: CancellationToken,
    worker: Option<JoinHandle<()>>,
}

impl Read for SharedResponse {
    fn read(&mut self, buffer: &mut [u8]) -> io::Result<usize> {
        if buffer.is_empty() {
            return Ok(0);
        }
        loop {
            let read = self.pending.read(buffer)?;
            if read != 0 {
                return Ok(read);
            }
            let Some(chunks) = self.chunks.as_ref() else {
                return Ok(0);
            };
            match chunks.recv() {
                Ok(Ok(chunk)) => self.pending = Cursor::new(chunk),
                Ok(Err(error)) => return Err(error),
                Err(_) => return Ok(0),
            }
        }
    }
}

impl Drop for SharedResponse {
    fn drop(&mut self) {
        self.cancellation.cancel();
        // Close the bounded channel before joining so a worker blocked in
        // send wakes immediately instead of deadlocking the synchronous drop.
        self.chunks.take();
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

fn run_shared_request(
    client: reqwest::Client,
    request: reqwest::Request,
    cancellation: CancellationToken,
    started: SyncSender<Result<()>>,
    chunks: SyncSender<io::Result<Vec<u8>>>,
) {
    let runtime = match tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => {
            let _ = started.send(Err(Error::transport(format!(
                "llmkit: create HTTP runtime: {error}"
            ))));
            return;
        }
    };
    runtime.block_on(async move {
        let mut response = match client.execute(request).await {
            Ok(response) => response,
            Err(error) => {
                let _ = started.send(Err(Error::transport(error.without_url().to_string())));
                return;
            }
        };
        let status = response.status().as_u16();
        if status >= 300 {
            let retry_after = response
                .headers()
                .get(reqwest::header::RETRY_AFTER)
                .and_then(|value| value.to_str().ok())
                .unwrap_or_default()
                .to_owned();
            let raw = match read_reqwest_limited(&mut response, MAX_ERROR_BODY).await {
                Ok(raw) => raw,
                Err(error) => {
                    let _ = started.send(Err(error));
                    return;
                }
            };
            let _ = started.send(Err(Error::http(status, &raw, &retry_after)));
            return;
        }
        if started.send(Ok(())).is_err() {
            return;
        }
        loop {
            let chunk = tokio::select! {
                biased;
                _ = cancellation.cancelled() => return,
                chunk = response.chunk() => chunk,
            };
            match chunk {
                Ok(Some(chunk)) => {
                    for piece in chunk.chunks(64 * 1024) {
                        if chunks.send(Ok(piece.to_vec())).is_err() {
                            return;
                        }
                    }
                }
                Ok(None) => return,
                Err(error) => {
                    let _ = chunks.send(Err(io::Error::other(error.without_url().to_string())));
                    return;
                }
            }
        }
    });
}

fn checked_header(
    name: &str,
    value: &str,
    invalid_name: &str,
    invalid_value: &str,
) -> Result<(http::header::HeaderName, http::header::HeaderValue)> {
    let name = http::header::HeaderName::from_bytes(name.as_bytes()).map_err(|error| {
        Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: {invalid_name}: {error}"),
        )
    })?;
    let value = http::header::HeaderValue::from_str(value).map_err(|error| {
        Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: {invalid_value}: {error}"),
        )
    })?;
    Ok((name, value))
}

fn join_url_path(base: &str, path: &str) -> Result<String> {
    let uri: http::Uri = base
        .parse()
        .map_err(|e| Error::local(ErrorCode::ProviderError, format!("llmkit: build url: {e}")))?;
    let mut parts = uri.into_parts();
    let base_path = parts
        .path_and_query
        .as_ref()
        .map_or("/", |value| value.path());
    let combined = format!("{base_path}/{path}");
    let mut segments = Vec::new();
    for segment in combined.split('/') {
        match segment {
            "" | "." => {}
            ".." => {
                segments.pop();
            }
            _ => segments.push(segment),
        }
    }
    let mut joined = format!("/{}", segments.join("/"));
    if path.ends_with('/') && !joined.ends_with('/') {
        joined.push('/');
    }
    if let Some(query) = parts
        .path_and_query
        .as_ref()
        .and_then(|value| value.query())
    {
        joined.push('?');
        joined.push_str(query);
    }
    parts.path_and_query =
        Some(joined.parse().map_err(|e| {
            Error::local(ErrorCode::ProviderError, format!("llmkit: build url: {e}"))
        })?);
    http::Uri::from_parts(parts)
        .map(|uri| uri.to_string())
        .map_err(|e| Error::local(ErrorCode::ProviderError, format!("llmkit: build url: {e}")))
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
    let parsed = base_url.parse::<http::Uri>();
    let (Some(scheme), Some(host)) = parsed
        .as_ref()
        .ok()
        .map(|uri| (uri.scheme_str(), uri.host()))
        .unwrap_or((None, None))
    else {
        return Err(Error::local(
            ErrorCode::AuthFailure,
            format!(
                "provider {:?} requires an HTTPS base URL for credentialed requests",
                descriptor.id
            ),
        ));
    };
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

fn is_loopback(host: &str) -> bool {
    if host.eq_ignore_ascii_case("localhost") {
        return true;
    }
    let host = host.trim_start_matches('[').trim_end_matches(']');
    host.parse::<IpAddr>().is_ok_and(|ip| ip.is_loopback())
}

pub(crate) fn read_limited(response: &mut SyncResponse, limit: u64) -> Result<Vec<u8>> {
    match response {
        SyncResponse::Ureq(response) => response
            .body_mut()
            .with_config()
            .limit(limit)
            .read_to_vec()
            .map_err(|error| Error::transport(error.to_string())),
        SyncResponse::Shared(response) => {
            let mut output = Vec::new();
            response
                .take(limit)
                .read_to_end(&mut output)
                .map_err(|error| Error::transport(error.to_string()))?;
            Ok(output)
        }
    }
}

pub(crate) async fn read_reqwest_limited(
    response: &mut reqwest::Response,
    limit: usize,
) -> Result<Vec<u8>> {
    let mut output = Vec::new();
    while output.len() < limit {
        let chunk = response
            .chunk()
            .await
            .map_err(|error| Error::transport(error.without_url().to_string()))?;
        let Some(chunk) = chunk else { break };
        let remaining = limit - output.len();
        output.extend_from_slice(&chunk[..chunk.len().min(remaining)]);
    }
    Ok(output)
}
