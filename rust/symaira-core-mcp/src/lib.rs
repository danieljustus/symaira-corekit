#![deny(unsafe_code)]

//! A deliberately small, owned MCP JSON-RPC stdio adapter.
//!
//! The adapter does not depend on an MCP SDK.  It keeps framing, request
//! validation, response encoding, and tool dispatch in one auditable boundary
//! so the wire contract remains independent of Rust framework defaults.

use serde::Serialize;
use serde::de::DeserializeOwned;
use serde_json::{Map, Value, value::RawValue};
use std::collections::BTreeMap;
use std::error::Error;
use std::fmt;
use std::io::{self, BufRead, BufReader, Read, Write};
use std::panic::{AssertUnwindSafe, catch_unwind};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex, mpsc};
use std::thread;
use std::time::Duration;
use thiserror::Error;

pub const PROTOCOL_VERSION: &str = "2024-11-05";
pub const MAX_LINE_BYTES: usize = 1 << 20;
pub const MAX_HEADER_BYTES: usize = 64 << 10;
pub const MAX_HEADER_LINES: usize = 100;

pub const CODE_PARSE_ERROR: i32 = -32700;
pub const CODE_INVALID_REQUEST: i32 = -32600;
pub const CODE_METHOD_NOT_FOUND: i32 = -32601;
pub const CODE_INVALID_PARAMS: i32 = -32602;
pub const CODE_INTERNAL_ERROR: i32 = -32603;
pub const TOOL_ERROR_META_KEY: &str = "symaira.dev/tool_error";

/// Cancellation shared with handlers and the cancellable transport entrypoint.
#[derive(Debug, Default)]
struct CancellationState {
    cancelled: AtomicBool,
}

/// Cooperative cancellation and per-request metadata exposed to handlers.
#[derive(Clone, Debug)]
pub struct CancellationToken {
    state: Arc<CancellationState>,
    request_meta: Arc<Mutex<Option<Map<String, Value>>>>,
}

impl CancellationToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.state.cancelled.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.state.cancelled.load(Ordering::Acquire)
    }

    /// Returns the request `_meta` object, when the caller supplied one.
    pub fn request_meta(&self) -> Option<Map<String, Value>> {
        self.request_meta.lock().ok().and_then(|meta| meta.clone())
    }

    fn with_request_meta(&self, meta: Option<Map<String, Value>>) -> Self {
        Self {
            state: Arc::clone(&self.state),
            request_meta: Arc::new(Mutex::new(meta)),
        }
    }
}

impl Default for CancellationToken {
    fn default() -> Self {
        Self {
            state: Arc::new(CancellationState::default()),
            request_meta: Arc::new(Mutex::new(None)),
        }
    }
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("{0}")]
pub struct RegistrationError(String);

impl RegistrationError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

/// MCP tool-behaviour hints. False values are omitted, matching the Go JSON
/// tags and preserving the distinction between an absent and true hint.
#[derive(Clone, Debug, Default, Serialize)]
pub struct ToolAnnotations {
    #[serde(skip_serializing_if = "String::is_empty")]
    pub title: String,
    #[serde(rename = "readOnlyHint", skip_serializing_if = "std::ops::Not::not")]
    pub read_only_hint: bool,
    #[serde(rename = "idempotentHint", skip_serializing_if = "std::ops::Not::not")]
    pub idempotent_hint: bool,
    #[serde(rename = "openWorldHint", skip_serializing_if = "std::ops::Not::not")]
    pub open_world_hint: bool,
    #[serde(rename = "destructiveHint", skip_serializing_if = "std::ops::Not::not")]
    pub destructive_hint: bool,
}

/// A JSON object in an MCP tool result.
pub type ContentBlock = Map<String, Value>;

/// A successful typed MCP tool result.
#[derive(Clone, Debug, Default)]
pub struct ToolResult {
    pub content: Vec<ContentBlock>,
    pub structured_content: Option<Value>,
    pub meta: Option<Map<String, Value>>,
}

impl ToolResult {
    pub fn text(text: impl Into<String>) -> Self {
        let mut block = Map::new();
        block.insert("text".to_string(), Value::String(text.into()));
        block.insert("type".to_string(), Value::String("text".to_string()));
        Self {
            content: vec![block],
            ..Self::default()
        }
    }

    fn into_value(self) -> Value {
        let mut result = Map::new();
        result.insert(
            "content".to_string(),
            Value::Array(self.content.into_iter().map(Value::Object).collect()),
        );
        result.insert("isError".to_string(), Value::Bool(false));
        if let Some(structured) = self.structured_content {
            result.insert("structuredContent".to_string(), structured);
        }
        if let Some(meta) = self.meta {
            result.insert("_meta".to_string(), Value::Object(meta));
        }
        Value::Object(result)
    }
}

/// Structured metadata for a tool-level failure.
#[derive(Debug, Default)]
pub struct ToolError {
    pub message: String,
    pub code: Option<String>,
    pub retryable: Option<bool>,
    pub requires_confirmation: Option<bool>,
    pub resume_hint: Option<String>,
    pub hint: Option<String>,
    pub details: Option<Map<String, Value>>,
    source: Option<Box<dyn Error + Send + Sync>>,
}

impl ToolError {
    pub fn new(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            ..Self::default()
        }
    }

    pub fn code(mut self, value: impl Into<String>) -> Self {
        self.code = Some(value.into());
        self
    }

    pub fn retryable(mut self, value: bool) -> Self {
        self.retryable = Some(value);
        self
    }

    pub fn requires_confirmation(mut self, value: bool) -> Self {
        self.requires_confirmation = Some(value);
        self
    }

    pub fn resume_hint(mut self, value: impl Into<String>) -> Self {
        self.resume_hint = Some(value.into());
        self
    }

    pub fn hint(mut self, value: impl Into<String>) -> Self {
        self.hint = Some(value.into());
        self
    }

    pub fn details(mut self, value: Map<String, Value>) -> Self {
        self.details = Some(value);
        self
    }

    /// Wraps an arbitrary error while retaining this error's structured metadata.
    pub fn source(mut self, source: impl Error + Send + Sync + 'static) -> Self {
        self.source = Some(Box::new(source));
        self
    }

    fn metadata(&self) -> Option<Value> {
        let mut data = Map::new();
        if let Some(value) = self.code.as_ref().filter(|value| !value.is_empty()) {
            data.insert("code".to_string(), Value::String(value.clone()));
        }
        if let Some(value) = self.retryable {
            data.insert("retryable".to_string(), Value::Bool(value));
        }
        if let Some(value) = self.requires_confirmation {
            data.insert("requires_confirmation".to_string(), Value::Bool(value));
        }
        if let Some(value) = self.resume_hint.as_ref().filter(|value| !value.is_empty()) {
            data.insert("resume_hint".to_string(), Value::String(value.clone()));
        }
        if let Some(value) = self.hint.as_ref().filter(|value| !value.is_empty()) {
            data.insert("hint".to_string(), Value::String(value.clone()));
        }
        if let Some(value) = self.details.as_ref().filter(|value| !value.is_empty()) {
            data.insert("details".to_string(), Value::Object(value.clone()));
        }
        if data.is_empty() {
            return None;
        }
        data.insert("message".to_string(), Value::String(self.message.clone()));
        Some(Value::Object(data))
    }
}

impl fmt::Display for ToolError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        self.message.fmt(formatter)
    }
}

impl Error for ToolError {
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        self.source
            .as_deref()
            .map(|source| source as &(dyn Error + 'static))
    }
}

/// Values returned by a tool handler.
#[derive(Clone, Debug)]
pub enum ToolOutput {
    /// Any value is rendered as one MCP text content block. Strings are
    /// rendered as their string value; all other JSON values use compact JSON.
    Value(Value),
    /// An already-shaped MCP result.
    Result(ToolResult),
}

impl From<Value> for ToolOutput {
    fn from(value: Value) -> Self {
        Self::Value(value)
    }
}

impl From<String> for ToolOutput {
    fn from(value: String) -> Self {
        Self::Value(Value::String(value))
    }
}

impl From<&str> for ToolOutput {
    fn from(value: &str) -> Self {
        Self::Value(Value::String(value.to_string()))
    }
}

impl From<ToolResult> for ToolOutput {
    fn from(value: ToolResult) -> Self {
        Self::Result(value)
    }
}

pub type ToolHandler = Arc<
    dyn Fn(CancellationToken, Value) -> Result<ToolOutput, Box<dyn Error + Send + Sync>>
        + Send
        + Sync,
>;

#[derive(Clone)]
pub struct Tool {
    pub name: String,
    pub description: String,
    pub input_schema: Option<Value>,
    pub annotations: Option<ToolAnnotations>,
    pub handler: Option<ToolHandler>,
}

impl fmt::Debug for Tool {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("Tool")
            .field("name", &self.name)
            .field("description", &self.description)
            .field("input_schema", &self.input_schema)
            .field("annotations", &self.annotations)
            .field("handler", &self.handler.as_ref().map(|_| "<handler>"))
            .finish()
    }
}

impl Tool {
    pub fn new(name: impl Into<String>, description: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            description: description.into(),
            input_schema: None,
            annotations: None,
            handler: None,
        }
    }

    pub fn schema(mut self, schema: Value) -> Self {
        self.input_schema = Some(schema);
        self
    }

    pub fn annotations(mut self, annotations: ToolAnnotations) -> Self {
        self.annotations = Some(annotations);
        self
    }

    pub fn handler<F>(mut self, handler: F) -> Self
    where
        F: Fn(CancellationToken, Value) -> Result<ToolOutput, Box<dyn Error + Send + Sync>>
            + Send
            + Sync
            + 'static,
    {
        self.handler = Some(Arc::new(handler));
        self
    }
}

const MAX_CONCURRENT_TOOL_CALLS: usize = 16;

struct ToolCallLimiter {
    state: Mutex<usize>,
    changed: Condvar,
}

struct ToolCallPermit {
    limiter: Arc<ToolCallLimiter>,
}

impl Drop for ToolCallPermit {
    fn drop(&mut self) {
        if let Ok(mut active) = self.limiter.state.lock() {
            *active = active.saturating_sub(1);
            self.limiter.changed.notify_one();
        }
    }
}

impl ToolCallLimiter {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            state: Mutex::new(0),
            changed: Condvar::new(),
        })
    }

    fn acquire(
        self: &Arc<Self>,
        token: &CancellationToken,
    ) -> Result<ToolCallPermit, TransportError> {
        let mut active = self
            .state
            .lock()
            .map_err(|_| TransportError::Write("tool call limiter mutex poisoned".to_string()))?;
        while *active >= MAX_CONCURRENT_TOOL_CALLS {
            if token.is_cancelled() {
                return Err(TransportError::Cancelled);
            }
            active = self
                .changed
                .wait_timeout(active, Duration::from_millis(10))
                .map_err(|_| TransportError::Write("tool call limiter mutex poisoned".to_string()))?
                .0;
        }
        if token.is_cancelled() {
            return Err(TransportError::Cancelled);
        }
        *active += 1;
        Ok(ToolCallPermit {
            limiter: Arc::clone(self),
        })
    }
}

#[derive(Clone)]
struct Registry {
    name: String,
    version: String,
    instructions: String,
    tools: BTreeMap<String, Tool>,
    order: Vec<String>,
}

/// A JSON-RPC 2.0 MCP server.
#[derive(Clone)]
pub struct Server {
    registry: Arc<Mutex<Registry>>,
}

impl fmt::Debug for Server {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        let registry = self.registry.lock().expect("MCP registry mutex poisoned");
        formatter
            .debug_struct("Server")
            .field("name", &registry.name)
            .field("version", &registry.version)
            .field("tool_count", &registry.tools.len())
            .finish()
    }
}

impl Server {
    pub fn new(name: impl Into<String>, version: impl Into<String>) -> Self {
        Self {
            registry: Arc::new(Mutex::new(Registry {
                name: name.into(),
                version: version.into(),
                instructions: String::new(),
                tools: BTreeMap::new(),
                order: Vec::new(),
            })),
        }
    }

    pub fn set_instructions(&self, instructions: impl Into<String>) {
        self.registry
            .lock()
            .expect("MCP registry mutex poisoned")
            .instructions = instructions.into();
    }

    pub fn register_tool(&self, tool: Tool) -> Result<(), RegistrationError> {
        if tool.name.is_empty() {
            return Err(RegistrationError::new(
                "mcp: RegisterTool called with empty Name",
            ));
        }
        let mut registry = self.registry.lock().expect("MCP registry mutex poisoned");
        if registry.tools.contains_key(&tool.name) {
            return Err(RegistrationError::new(format!(
                "mcp: duplicate tool registration: {}",
                tool.name
            )));
        }
        registry.order.push(tool.name.clone());
        registry.tools.insert(tool.name.clone(), tool);
        Ok(())
    }

    /// Optional seam used by parity fixtures to exercise Go's nil boundary.
    pub fn register_optional_tool(&self, tool: Option<Tool>) -> Result<(), RegistrationError> {
        let Some(tool) = tool else {
            return Err(RegistrationError::new(
                "mcp: RegisterTool called with nil Tool",
            ));
        };
        self.register_tool(tool)
    }

    /// Registers a typed input and derives its JSON Schema from `T`.
    pub fn register_typed<T, F>(
        &self,
        name: impl Into<String>,
        description: impl Into<String>,
        handler: F,
    ) -> Result<(), RegistrationError>
    where
        T: DeserializeOwned + schemars::JsonSchema + Send + 'static,
        F: Fn(CancellationToken, T) -> Result<ToolOutput, Box<dyn Error + Send + Sync>>
            + Send
            + Sync
            + 'static,
    {
        let name = name.into();
        let handler_name = name.clone();
        let schema_source = serde_json::to_value(schemars::schema_for!(T))
            .map_err(|error| RegistrationError::new(format!("mcp: schema for {name}: {error}")))?;
        let mut schema = schema_source.clone();
        normalize_schema_for_go(&mut schema);
        let is_struct_schema = schema.get("type") == Some(&Value::String("object".to_string()))
            && schema.get("properties").is_some()
            && schema.get("additionalProperties").is_none();
        if !is_struct_schema {
            return Err(RegistrationError::new(format!(
                "mcp: RegisterTyped({name}) requires a struct input"
            )));
        }
        let validation_schema = schema.clone();
        let typed_handler = move |token: CancellationToken, input: Value| {
            let mut args = if input.is_null() {
                Value::Object(Map::new())
            } else {
                input
            };
            apply_go_zero_defaults(&mut args, &validation_schema, &schema_source);
            if let Err(path) = reject_unknown_fields(&args, &validation_schema, "") {
                return Err(Box::new(ToolError::new(format!(
                    "invalid arguments for {handler_name}: json: unknown field \"{path}\""
                ))) as Box<dyn Error + Send + Sync>);
            }
            let bytes = serde_json::to_vec(&args).map_err(|error| {
                Box::new(ToolError::new(format!(
                    "invalid arguments for {handler_name}: {error}"
                ))) as Box<dyn Error + Send + Sync>
            })?;
            let mut deserializer = serde_json::Deserializer::from_slice(&bytes);
            let mut ignored = Vec::new();
            let typed = serde_ignored::deserialize(&mut deserializer, |path| {
                ignored.push(path.to_string())
            })
            .map_err(|error| {
                Box::new(ToolError::new(format!(
                    "invalid arguments for {handler_name}: {error}"
                ))) as Box<dyn Error + Send + Sync>
            })?;
            if let Some(path) = ignored.first() {
                return Err(Box::new(ToolError::new(format!(
                    "invalid arguments for {handler_name}: json: unknown field \"{path}\""
                ))) as Box<dyn Error + Send + Sync>);
            }
            handler(token, typed)
        };
        self.register_tool(
            Tool::new(name, description)
                .schema(schema)
                .handler(typed_handler),
        )
    }

    pub fn serve_stdio(&self) -> Result<(), TransportError> {
        self.serve_io(io::stdin(), io::stdout())
    }

    /// Serve a synchronous reader/writer pair. Tool calls run concurrently;
    /// all complete responses are serialized under one writer lock. Normal EOF
    /// waits for every in-flight call.
    pub fn serve_io<R: Read + Send + 'static, W: Write + Send + 'static>(
        &self,
        reader: R,
        writer: W,
    ) -> Result<(), TransportError> {
        self.serve_io_cancellable(reader, writer, CancellationToken::new())
    }

    /// Serve an owned reader while allowing cancellation to return even when
    /// the reader is not closable. The reader thread is deliberately not joined
    /// on cancellation; waiting for an arbitrary blocking Read would deadlock.
    pub fn serve_io_cancellable<R, W>(
        &self,
        reader: R,
        writer: W,
        token: CancellationToken,
    ) -> Result<(), TransportError>
    where
        R: Read + Send + 'static,
        W: Write + Send + 'static,
    {
        let (sender, receiver) = mpsc::sync_channel(1);
        let parser_token = token.clone();
        let parser = thread::Builder::new()
            .name("symaira-mcp-parser".to_string())
            .spawn(move || {
                let mut buffered = BufReader::new(reader);
                loop {
                    let item = read_request(&mut buffered);
                    let terminal = item_is_terminal(&item);
                    if sender.send(item).is_err() || parser_token.is_cancelled() {
                        return;
                    }
                    if terminal {
                        return;
                    }
                }
            })
            .map_err(|error| TransportError::Write(format!("spawn parser: {error}")))?;
        let shared_writer = Arc::new(Mutex::new(writer));
        let terminal_error = Arc::new(Mutex::new(None));
        let result = self.serve_channel(
            receiver,
            shared_writer,
            token.clone(),
            terminal_error,
            ToolCallLimiter::new(),
        );
        if !token.is_cancelled() {
            parser
                .join()
                .map_err(|_| TransportError::Read("parser thread panicked".to_string()))?;
        }
        result
    }

    fn serve_channel<W: Write + Send + 'static>(
        &self,
        receiver: mpsc::Receiver<ReadItem>,
        writer: Arc<Mutex<W>>,
        token: CancellationToken,
        terminal_error: Arc<Mutex<Option<TransportError>>>,
        limiter: Arc<ToolCallLimiter>,
    ) -> Result<(), TransportError> {
        let mut jobs = Vec::new();
        loop {
            if token.is_cancelled() {
                let error = terminal_error.lock().ok().and_then(|error| error.clone());
                return Err(error.unwrap_or(TransportError::Cancelled));
            }
            match receiver.recv_timeout(std::time::Duration::from_millis(10)) {
                Ok(item) => {
                    let terminal = item_is_terminal(&item);
                    match self.dispatch_item(
                        item,
                        Arc::clone(&writer),
                        token.clone(),
                        Arc::clone(&terminal_error),
                        Arc::clone(&limiter),
                    ) {
                        Ok(Some(job)) => jobs.push(job),
                        Ok(None) => {}
                        Err(error) => {
                            token.cancel();
                            return Err(error);
                        }
                    }
                    if terminal {
                        if token.is_cancelled() {
                            let error = terminal_error.lock().ok().and_then(|error| error.clone());
                            return Err(error.unwrap_or(TransportError::Cancelled));
                        }
                        return Self::wait_jobs(jobs);
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => continue,
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    if token.is_cancelled() {
                        let error = terminal_error.lock().ok().and_then(|error| error.clone());
                        return Err(error.unwrap_or(TransportError::Cancelled));
                    }
                    return Self::wait_jobs(jobs);
                }
            }
        }
    }

    fn dispatch_item<W: Write + Send + 'static>(
        &self,
        item: ReadItem,
        writer: Arc<Mutex<W>>,
        token: CancellationToken,
        terminal_error: Arc<Mutex<Option<TransportError>>>,
        limiter: Arc<ToolCallLimiter>,
    ) -> Result<Option<thread::JoinHandle<Result<(), TransportError>>>, TransportError> {
        match item {
            ReadItem::Request(request, mode) if request.method == "tools/call" => {
                let permit = limiter.acquire(&token)?;
                let server = self.clone();
                let job_error = Arc::clone(&terminal_error);
                let job = thread::Builder::new()
                    .name("symaira-mcp-tool".to_string())
                    .spawn(move || {
                        let result = catch_unwind(AssertUnwindSafe(|| {
                            server.handle_request(request, mode, Arc::clone(&writer), token.clone())
                        }));
                        let result = match result {
                            Ok(result) => result,
                            Err(_) => Err(TransportError::Write("handler panicked".to_string())),
                        };
                        if let Err(error) = &result {
                            match job_error.lock() {
                                Ok(mut first_error) if first_error.is_none() => {
                                    *first_error = Some(error.clone());
                                }
                                _ => {}
                            }
                            token.cancel();
                        }
                        drop(permit);
                        result
                    })
                    .map_err(|error| {
                        TransportError::Write(format!("spawn tool handler: {error}"))
                    })?;
                Ok(Some(job))
            }
            ReadItem::Request(request, mode) => self
                .handle_request(request, mode, writer, token)
                .map(|_| None),
            ReadItem::ProtocolError(error, mode) => {
                let response = match error {
                    ProtocolErrorKind::Parse(message) => rpc_error(
                        raw_null(),
                        CODE_PARSE_ERROR,
                        format!("Parse error: {message}"),
                    ),
                    ProtocolErrorKind::InvalidRequest => rpc_error(
                        raw_null(),
                        CODE_INVALID_REQUEST,
                        "Invalid Request".to_string(),
                    ),
                    ProtocolErrorKind::Transport(message) => {
                        return Err(TransportError::Read(message));
                    }
                };
                write_frame(&writer, mode, &response).map(|_| None)
            }
            ReadItem::Eof => Ok(None),
        }
    }

    fn wait_jobs(
        jobs: Vec<thread::JoinHandle<Result<(), TransportError>>>,
    ) -> Result<(), TransportError> {
        let mut first_error = None;
        for job in jobs {
            match job.join() {
                Ok(Ok(())) => {}
                Ok(Err(error)) if first_error.is_none() => first_error = Some(error),
                Ok(Err(_)) => {}
                Err(_) if first_error.is_none() => {
                    first_error = Some(TransportError::Write("handler panicked".to_string()))
                }
                Err(_) => {}
            }
        }
        first_error.map_or(Ok(()), Err)
    }

    fn handle_request<W: Write + Send + 'static>(
        &self,
        request: Request,
        mode: ResponseMode,
        writer: Arc<Mutex<W>>,
        token: CancellationToken,
    ) -> Result<(), TransportError> {
        let response = match request.method.as_str() {
            "initialize" => {
                let registry = self
                    .registry
                    .lock()
                    .expect("MCP registry mutex poisoned")
                    .clone();
                let mut result = Map::new();
                result.insert(
                    "protocolVersion".to_string(),
                    Value::String(PROTOCOL_VERSION.to_string()),
                );
                let mut capabilities = Map::new();
                capabilities.insert("tools".to_string(), Value::Object(Map::new()));
                result.insert("capabilities".to_string(), Value::Object(capabilities));
                result.insert(
                    "serverInfo".to_string(),
                    serde_json::json!({"name": registry.name, "version": registry.version}),
                );
                if !registry.instructions.is_empty() {
                    result.insert(
                        "instructions".to_string(),
                        Value::String(registry.instructions),
                    );
                }
                Some(rpc_result(request.id, Value::Object(result)))
            }
            "ping" => Some(rpc_result(request.id, Value::Object(Map::new()))),
            "tools/list" => {
                let registry = self
                    .registry
                    .lock()
                    .expect("MCP registry mutex poisoned")
                    .clone();
                let tools = registry
                    .order
                    .iter()
                    .filter_map(|name| registry.tools.get(name))
                    .map(|tool| ToolDescriptionWire {
                        annotations: tool.annotations.clone(),
                        description: tool.description.clone(),
                        input_schema: tool.input_schema.clone(),
                        name: tool.name.clone(),
                    })
                    .collect::<Vec<_>>();
                Some(rpc_tools_result(request.id, tools))
            }
            "tools/call" => match self.call_tool(&request, token.clone()) {
                Ok(result) => Some(rpc_result(request.id, result)),
                Err(error) => Some(rpc_error(request.id, error.code, error.message)),
            },
            _ => Some(rpc_error(
                request.id,
                CODE_METHOD_NOT_FOUND,
                format!("Method not found: {}", request.method),
            )),
        };
        if request.notification || response.is_none() {
            return Ok(());
        }
        write_frame(&writer, mode, &response.expect("response checked above"))
    }

    fn call_tool(&self, request: &Request, token: CancellationToken) -> Result<Value, CallError> {
        let params = match request.params.as_ref() {
            Some(Value::Object(params)) => params,
            Some(Value::Array(_)) => {
                return Err(CallError::rpc(
                    CODE_INVALID_PARAMS,
                    r#"Invalid params: json: cannot unmarshal array into Go value of type struct { Name string "json:\"name\""; Arguments json.RawMessage "json:\"arguments\""; Meta map[string]interface {} "json:\"_meta,omitempty\"" }"#,
                ));
            }
            None => {
                return Err(CallError::rpc(
                    CODE_INVALID_PARAMS,
                    "Invalid params: unexpected end of JSON input",
                ));
            }
            Some(_) => {
                return Err(CallError::rpc(
                    CODE_INVALID_PARAMS,
                    "Invalid params: expected an object",
                ));
            }
        };
        let name = match params.get("name") {
            None => "",
            Some(Value::String(name)) => name.as_str(),
            Some(_) => {
                return Err(CallError::rpc(
                    CODE_INVALID_PARAMS,
                    "Invalid params: json: cannot unmarshal number into Go struct field .name of type string",
                ));
            }
        };
        let request_meta = match params.get("_meta") {
            None => None,
            Some(Value::Object(meta)) => Some(meta.clone()),
            Some(_) => {
                return Err(CallError::rpc(
                    CODE_INVALID_PARAMS,
                    "Invalid params: json: cannot unmarshal non-object into Go struct field ._meta of type map[string]interface {}",
                ));
            }
        };
        let registry = self
            .registry
            .lock()
            .expect("MCP registry mutex poisoned")
            .clone();
        let Some(tool) = registry.tools.get(name) else {
            return Err(CallError::rpc(
                CODE_METHOD_NOT_FOUND,
                format!("Unknown tool: {name}"),
            ));
        };
        let Some(handler) = tool.handler.as_ref() else {
            return Err(CallError::rpc(
                CODE_INTERNAL_ERROR,
                format!("Tool has no handler: {name}"),
            ));
        };
        let arguments = params.get("arguments").cloned().unwrap_or(Value::Null);
        let request_token = token.with_request_meta(request_meta);
        let output = catch_unwind(AssertUnwindSafe(|| handler(request_token, arguments)));
        match output {
            Ok(Ok(ToolOutput::Result(result))) => Ok(result.into_value()),
            Ok(Ok(ToolOutput::Value(value))) => Ok(text_result(value)),
            Ok(Err(error)) => Ok(tool_error_result(error.as_ref())),
            Err(_) => Err(CallError::rpc(
                CODE_INTERNAL_ERROR,
                "Internal error: handler panicked",
            )),
        }
    }
}

/// Errors returned by the transport itself. Protocol errors are written to the
/// selected response mode and do not become this error.
#[derive(Clone, Debug, Error, Eq, PartialEq)]
pub enum TransportError {
    #[error("mcpserver: read error: {0}")]
    Read(String),
    #[error("mcpserver: write response: {0}")]
    Write(String),
    #[error("cancelled")]
    Cancelled,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum ResponseMode {
    Line,
    Framed,
}

#[derive(Debug)]
enum ReadItem {
    Request(Request, ResponseMode),
    ProtocolError(ProtocolErrorKind, ResponseMode),
    Eof,
}

fn item_is_terminal(item: &ReadItem) -> bool {
    matches!(
        item,
        ReadItem::Eof | ReadItem::ProtocolError(ProtocolErrorKind::Transport(_), _)
    )
}

#[derive(Debug)]
enum ProtocolErrorKind {
    Parse(String),
    InvalidRequest,
    Transport(String),
}

#[derive(Debug)]
struct Request {
    id: Box<RawValue>,
    notification: bool,
    method: String,
    params: Option<Value>,
}

#[derive(Debug)]
struct CallError {
    code: i32,
    message: String,
}

impl CallError {
    fn rpc(code: i32, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

#[derive(Serialize)]
struct RpcResponse {
    jsonrpc: &'static str,
    id: Box<RawValue>,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<ResponseResult>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<RpcError>,
}

#[derive(Serialize)]
enum ResponseResult {
    #[serde(untagged)]
    Value(Value),
    #[serde(untagged)]
    Tools(ToolsListResult),
}

#[derive(Serialize)]
struct ToolsListResult {
    tools: Vec<ToolDescriptionWire>,
}

#[derive(Serialize)]
struct ToolDescriptionWire {
    #[serde(skip_serializing_if = "Option::is_none")]
    annotations: Option<ToolAnnotations>,
    description: String,
    #[serde(rename = "inputSchema", skip_serializing_if = "Option::is_none")]
    input_schema: Option<Value>,
    name: String,
}

#[derive(Serialize)]
struct RpcError {
    code: i32,
    message: String,
}

fn raw_null() -> Box<RawValue> {
    RawValue::from_string("null".to_string()).expect("null is valid JSON")
}

fn rpc_result(id: Box<RawValue>, result: Value) -> RpcResponse {
    RpcResponse {
        jsonrpc: "2.0",
        id,
        result: Some(ResponseResult::Value(result)),
        error: None,
    }
}

fn rpc_tools_result(id: Box<RawValue>, tools: Vec<ToolDescriptionWire>) -> RpcResponse {
    RpcResponse {
        jsonrpc: "2.0",
        id,
        result: Some(ResponseResult::Tools(ToolsListResult { tools })),
        error: None,
    }
}

fn rpc_error(id: Box<RawValue>, code: i32, message: String) -> RpcResponse {
    RpcResponse {
        jsonrpc: "2.0",
        id,
        result: None,
        error: Some(RpcError { code, message }),
    }
}

fn normalize_schema_for_go(schema: &mut Value) {
    let definitions = schema
        .get("$defs")
        .cloned()
        .unwrap_or_else(|| Value::Object(Map::new()));
    normalize_schema_value(schema, &definitions);
    if let Value::Object(object) = schema {
        object.remove("$schema");
        object.remove("$defs");
        object.remove("title");
    }
}

fn normalize_schema_value(value: &mut Value, definitions: &Value) {
    if let Value::Object(object) = value {
        if let Some(Value::String(reference)) = object.get("$ref")
            && let Some(name) = reference.strip_prefix("#/$defs/")
            && let Some(mut resolved) = definitions.get(name).cloned()
        {
            normalize_schema_value(&mut resolved, definitions);
            *value = resolved;
            return;
        }
        if let Some(Value::Array(variants)) = object.get("anyOf") {
            let non_null = variants
                .iter()
                .filter(|variant| variant.get("type") != Some(&Value::String("null".to_string())))
                .cloned()
                .collect::<Vec<_>>();
            if non_null.len() == 1 && variants.len() == 2 {
                *value = non_null.into_iter().next().expect("one non-null schema");
                normalize_schema_value(value, definitions);
                return;
            }
        }
        object.remove("$schema");
        object.remove("title");
        object.remove("$defs");
        for child in object.values_mut() {
            normalize_schema_value(child, definitions);
        }
    } else if let Value::Array(items) = value {
        for item in items {
            normalize_schema_value(item, definitions);
        }
    }
}

fn apply_go_zero_defaults(value: &mut Value, schema: &Value, source_schema: &Value) {
    match (value, schema) {
        (Value::Object(fields), Value::Object(schema)) => {
            if let Some(Value::Object(properties)) = schema.get("properties") {
                let source_properties = source_schema.get("properties");
                for (name, property_schema) in properties {
                    if !fields.contains_key(name) {
                        let source_property =
                            source_properties.and_then(|properties| properties.get(name));
                        fields.insert(
                            name.clone(),
                            if source_property.is_some_and(schema_allows_null) {
                                Value::Null
                            } else {
                                schema_zero_value(property_schema)
                            },
                        );
                    }
                }
                for (name, field) in fields.iter_mut() {
                    if let Some(property_schema) = properties.get(name) {
                        let source_property =
                            source_properties.and_then(|properties| properties.get(name));
                        apply_go_zero_defaults(
                            field,
                            property_schema,
                            source_property.unwrap_or(property_schema),
                        );
                    }
                }
            }
        }
        (Value::Array(items), Value::Object(schema)) => {
            if let Some(item_schema) = schema.get("items") {
                let source_item_schema = source_schema.get("items").unwrap_or(item_schema);
                for item in items {
                    apply_go_zero_defaults(item, item_schema, source_item_schema);
                }
            }
        }
        _ => {}
    }
}

fn schema_allows_null(schema: &Value) -> bool {
    schema
        .get("anyOf")
        .and_then(Value::as_array)
        .is_some_and(|variants| {
            variants
                .iter()
                .any(|variant| variant.get("type") == Some(&Value::String("null".to_string())))
        })
}

fn schema_zero_value(schema: &Value) -> Value {
    match schema.get("type").and_then(Value::as_str) {
        Some("string") => Value::String(String::new()),
        Some("boolean") => Value::Bool(false),
        Some("integer") | Some("number") => Value::Number(0.into()),
        Some("array") => Value::Array(Vec::new()),
        Some("object") => {
            let mut value = Value::Object(Map::new());
            apply_go_zero_defaults(&mut value, schema, schema);
            value
        }
        _ => Value::Null,
    }
}

fn reject_unknown_fields(input: &Value, schema: &Value, path: &str) -> Result<(), String> {
    match (input, schema) {
        (Value::Object(fields), Value::Object(schema)) => {
            if let Some(Value::Object(properties)) = schema.get("properties") {
                for (name, value) in fields {
                    let Some(property_schema) = properties.get(name) else {
                        return Err(if path.is_empty() {
                            name.clone()
                        } else {
                            format!("{path}.{name}")
                        });
                    };
                    let child_path = if path.is_empty() {
                        name.clone()
                    } else {
                        format!("{path}.{name}")
                    };
                    reject_unknown_fields(value, property_schema, &child_path)?;
                }
            }
        }
        (Value::Array(items), Value::Object(schema)) => {
            if let Some(item_schema) = schema.get("items") {
                for item in items {
                    reject_unknown_fields(item, item_schema, path)?;
                }
            }
        }
        _ => {}
    }
    Ok(())
}

fn text_result(value: Value) -> Value {
    let text = match value {
        Value::String(text) => text,
        value => {
            String::from_utf8(go_json_bytes(&value).expect("serde_json::Value is serializable"))
                .expect("JSON output is UTF-8")
        }
    };
    let mut block = Map::new();
    block.insert("type".to_string(), Value::String("text".to_string()));
    block.insert("text".to_string(), Value::String(text));
    let mut result = Map::new();
    result.insert(
        "content".to_string(),
        Value::Array(vec![Value::Object(block)]),
    );
    result.insert("isError".to_string(), Value::Bool(false));
    Value::Object(result)
}

fn tool_error_result(error: &(dyn Error + 'static)) -> Value {
    let mut block = Map::new();
    block.insert("type".to_string(), Value::String("text".to_string()));
    block.insert("text".to_string(), Value::String(error.to_string()));
    let mut result = Map::new();
    result.insert(
        "content".to_string(),
        Value::Array(vec![Value::Object(block)]),
    );
    result.insert("isError".to_string(), Value::Bool(true));
    let mut current = Some(error);
    while let Some(candidate) = current {
        if let Some(tool_error) = candidate.downcast_ref::<ToolError>()
            && let Some(metadata) = tool_error.metadata()
        {
            let mut meta = Map::new();
            let mut metadata = metadata;
            if let Value::Object(fields) = &mut metadata {
                fields.insert("message".to_string(), Value::String(error.to_string()));
            }
            meta.insert(TOOL_ERROR_META_KEY.to_string(), metadata);
            result.insert("_meta".to_string(), Value::Object(meta));
            break;
        }
        current = candidate.source();
    }
    Value::Object(result)
}

fn go_json_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, serde_json::Error> {
    let mut encoded = serde_json::to_vec(value)?;
    // Go's encoding/json escapes these HTML-sensitive bytes and the two JSON
    // line-separator code points everywhere, including inside RawValue fields.
    // They cannot occur as JSON syntax outside strings, so a byte-level pass is
    // both smaller and safer than re-parsing arbitrary structured values.
    let mut escaped = Vec::with_capacity(encoded.len());
    let mut index = 0;
    while index < encoded.len() {
        let replacement = match encoded[index] {
            b'<' => Some((b"\\u003c".as_slice(), 1)),
            b'>' => Some((b"\\u003e".as_slice(), 1)),
            b'&' => Some((b"\\u0026".as_slice(), 1)),
            _ if encoded[index..].starts_with("\u{2028}".as_bytes()) => {
                Some((b"\\u2028".as_slice(), 3))
            }
            _ if encoded[index..].starts_with("\u{2029}".as_bytes()) => {
                Some((b"\\u2029".as_slice(), 3))
            }
            _ => None,
        };
        if let Some((replacement, original_len)) = replacement {
            escaped.extend_from_slice(replacement);
            index += original_len;
        } else {
            escaped.push(encoded[index]);
            index += 1;
        }
    }
    encoded.clear();
    encoded.extend_from_slice(&escaped);
    Ok(encoded)
}

fn write_frame<W: Write + Send + 'static>(
    writer: &Arc<Mutex<W>>,
    mode: ResponseMode,
    response: &RpcResponse,
) -> Result<(), TransportError> {
    let body = go_json_bytes(response)
        .map_err(|error| TransportError::Write(format!("marshal response: {error}")))?;
    let mut frame = Vec::with_capacity(body.len() + 64);
    match mode {
        ResponseMode::Line => {
            frame.extend_from_slice(&body);
            frame.push(b'\n');
        }
        ResponseMode::Framed => {
            frame.extend_from_slice(format!("Content-Length: {}\r\n\r\n", body.len()).as_bytes());
            frame.extend_from_slice(&body);
        }
    }
    let mut output = writer
        .lock()
        .map_err(|_| TransportError::Write("writer mutex poisoned".to_string()))?;
    output
        .write_all(&frame)
        .map_err(|error| TransportError::Write(error.to_string()))?;
    output
        .flush()
        .map_err(|error| TransportError::Write(error.to_string()))
}

fn read_request<R: BufRead>(reader: &mut R) -> ReadItem {
    let (first, first_bytes) = match read_nonempty_line(reader) {
        Ok(Some(line)) => line,
        Ok(None) => return ReadItem::Eof,
        Err(error) => {
            return ReadItem::ProtocolError(
                ProtocolErrorKind::Transport(error),
                ResponseMode::Framed,
            );
        }
    };
    let trimmed = first.trim().to_string();
    if looks_like_json_line(&trimmed) {
        return parse_json_request(trimmed.as_bytes(), ResponseMode::Line);
    }
    if first_bytes > MAX_HEADER_BYTES {
        return ReadItem::ProtocolError(
            ProtocolErrorKind::Transport("framed header limits exceeded".to_string()),
            ResponseMode::Framed,
        );
    }

    let mut header_bytes = first_bytes;
    let mut header_lines = 1;
    let mut content_length = None;
    if let Err(error) = parse_content_length(&trimmed, &mut content_length) {
        return ReadItem::ProtocolError(ProtocolErrorKind::Transport(error), ResponseMode::Framed);
    }
    loop {
        // The terminating blank line is framing, not a header. Permit its
        // CRLF beyond an otherwise exact aggregate header-byte boundary.
        let line_limit = MAX_HEADER_BYTES - header_bytes + 2;
        let line = match read_limited_line(reader, line_limit) {
            Ok(Some(line)) => line,
            Ok(None) => return ReadItem::Eof,
            Err(error) => {
                return ReadItem::ProtocolError(
                    ProtocolErrorKind::Transport(error),
                    ResponseMode::Framed,
                );
            }
        };
        if !line.ends_with('\n') {
            // Go's bufio reader treats a header fragment ending at EOF as a
            // clean stream termination rather than a transport failure.
            return ReadItem::Eof;
        }
        let header = line.trim_end_matches(['\r', '\n']);
        if header.is_empty() {
            break;
        }
        header_bytes += line.len();
        header_lines += 1;
        if header_bytes > MAX_HEADER_BYTES || header_lines > MAX_HEADER_LINES {
            return ReadItem::ProtocolError(
                ProtocolErrorKind::Transport("framed header limits exceeded".to_string()),
                ResponseMode::Framed,
            );
        }
        if let Err(error) = parse_content_length(header, &mut content_length) {
            return ReadItem::ProtocolError(
                ProtocolErrorKind::Transport(error),
                ResponseMode::Framed,
            );
        }
    }
    let Some(length) = content_length else {
        return ReadItem::ProtocolError(
            ProtocolErrorKind::Transport("missing Content-Length header".to_string()),
            ResponseMode::Framed,
        );
    };
    if length == 0 || length > MAX_LINE_BYTES {
        return ReadItem::ProtocolError(
            ProtocolErrorKind::Transport(format!("invalid Content-Length: {length}")),
            ResponseMode::Framed,
        );
    }
    let mut body = vec![0_u8; length];
    if let Err(error) = reader.read_exact(&mut body) {
        return ReadItem::ProtocolError(
            ProtocolErrorKind::Transport(format!("read body: {error}")),
            ResponseMode::Framed,
        );
    }
    parse_json_request(&body, ResponseMode::Framed)
}

fn parse_content_length(line: &str, output: &mut Option<usize>) -> Result<(), String> {
    if let Some(rest) = line.strip_prefix("Content-Length:") {
        let value = rest.trim();
        let length = value
            .parse::<usize>()
            .map_err(|_| format!("invalid Content-Length: {value:?}"))?;
        *output = Some(length);
    }
    Ok(())
}

fn looks_like_json_line(line: &str) -> bool {
    if serde_json::from_str::<Value>(line).is_ok() {
        return true;
    }
    match line.as_bytes().first().copied() {
        Some(b'{') | Some(b'[') | Some(b'"') | Some(b'-') | Some(b't') | Some(b'f')
        | Some(b'n') => true,
        Some(byte) if byte.is_ascii_digit() => true,
        _ => false,
    }
}

fn parse_json_request(data: &[u8], mode: ResponseMode) -> ReadItem {
    let document = match serde_json::from_slice::<Value>(data) {
        Ok(document) => document,
        Err(error) => {
            return ReadItem::ProtocolError(
                ProtocolErrorKind::Parse(go_like_json_error(data, &error.to_string())),
                mode,
            );
        }
    };
    if !document.is_object() {
        return ReadItem::ProtocolError(ProtocolErrorKind::InvalidRequest, mode);
    }
    let fields = match serde_json::from_value::<BTreeMap<String, Box<RawValue>>>(document) {
        Ok(fields) => fields,
        Err(error) => {
            return ReadItem::ProtocolError(
                ProtocolErrorKind::Parse(go_like_json_error(data, &error.to_string())),
                mode,
            );
        }
    };
    let jsonrpc = fields
        .get("jsonrpc")
        .and_then(|raw| serde_json::from_str::<String>(raw.get()).ok());
    let method = fields
        .get("method")
        .and_then(|raw| serde_json::from_str::<String>(raw.get()).ok());
    let Some(method) = method.filter(|method| !method.is_empty()) else {
        return ReadItem::ProtocolError(ProtocolErrorKind::InvalidRequest, mode);
    };
    if jsonrpc.as_deref() != Some("2.0") {
        return ReadItem::ProtocolError(ProtocolErrorKind::InvalidRequest, mode);
    }
    let (notification, id) = match fields.get("id") {
        None => (true, raw_null()),
        Some(raw) if valid_raw_id(raw.get()) => (false, raw.clone()),
        Some(_) => return ReadItem::ProtocolError(ProtocolErrorKind::InvalidRequest, mode),
    };
    let params = match fields.get("params") {
        None => None,
        Some(raw) => match serde_json::from_str::<Value>(raw.get()) {
            Ok(value) if value.is_object() || value.is_array() => Some(value),
            _ => return ReadItem::ProtocolError(ProtocolErrorKind::InvalidRequest, mode),
        },
    };
    ReadItem::Request(
        Request {
            id,
            notification,
            method,
            params,
        },
        mode,
    )
}

fn valid_raw_id(raw: &str) -> bool {
    let trimmed = raw.trim();
    if trimmed == "null" || trimmed.starts_with('"') {
        return trimmed == "null" || trimmed.starts_with('"');
    }
    if let Some(rest) = trimmed.strip_prefix('-') {
        return rest.as_bytes().first().is_some_and(u8::is_ascii_digit);
    }
    trimmed.as_bytes().first().is_some_and(u8::is_ascii_digit)
}

fn go_like_json_error(data: &[u8], serde_message: &str) -> String {
    let trimmed = data.strip_suffix(b"\n").unwrap_or(data);
    if serde_message.contains("key must be a string") || serde_message.contains("trailing comma") {
        let mut candidate = None;
        for (index, byte) in trimmed.iter().enumerate() {
            if (*byte == b'{' || *byte == b',') && index + 1 < trimmed.len() {
                let next = trimmed[index + 1..]
                    .iter()
                    .copied()
                    .find(|byte| !byte.is_ascii_whitespace());
                if next.is_some_and(|byte| byte != b'\"') {
                    candidate = next;
                    break;
                }
            }
        }
        if let Some(byte) = candidate {
            return format!(
                "invalid character '{}' looking for beginning of object key string",
                char::from(byte)
            );
        }
    }
    if let (true, Some(byte)) = (
        serde_message.contains("expected value"),
        serde_error_column_byte(trimmed, serde_message),
    ) {
        return format!(
            "invalid character '{}' looking for beginning of value",
            char::from(byte)
        );
    }
    if serde_message.contains("EOF while parsing") {
        return "unexpected end of JSON input".to_string();
    }
    if serde_message.contains("trailing characters") {
        let trailing = trimmed
            .iter()
            .position(|byte| *byte == b'}' || *byte == b']')
            .and_then(|index| {
                trimmed[index + 1..]
                    .iter()
                    .position(|byte| !byte.is_ascii_whitespace())
                    .map(|offset| index + 1 + offset)
            });
        if let Some(index) = trailing {
            return format!(
                "invalid character '{}' after top-level value",
                char::from(trimmed[index])
            );
        }
    }
    if serde_message.contains("expected ident") {
        let first = trimmed.iter().position(|byte| !byte.is_ascii_whitespace());
        if let Some(index) = first {
            let (prefix, literal, expected, offset) = if trimmed[index..].starts_with(b"nul") {
                (b"nul".as_slice(), "null", 'l', 3)
            } else if trimmed[index..].starts_with(b"tru") {
                (b"tru".as_slice(), "true", 'e', 3)
            } else if trimmed[index..].starts_with(b"fals") {
                (b"fals".as_slice(), "false", 'e', 4)
            } else {
                match trimmed[index] {
                    b'n' => (b"n".as_slice(), "null", 'u', 1),
                    b't' => (b"t".as_slice(), "true", 'r', 1),
                    b'f' => (b"f".as_slice(), "false", 'a', 1),
                    _ => (&[][..], "", '\0', 0),
                }
            };
            if !prefix.is_empty()
                && let Some(byte) = trimmed.get(index + offset)
            {
                return format!(
                    "invalid character '{}' in literal {literal} (expecting '{expected}')",
                    char::from(*byte)
                );
            }
        }
    }
    if serde_message.contains("invalid escape") {
        let escaped = trimmed
            .iter()
            .position(|byte| *byte == b'\\')
            .and_then(|index| trimmed.get(index + 1).copied());
        if let Some(byte) = escaped {
            return format!(
                "invalid character '{}' in string escape code",
                char::from(byte)
            );
        }
    }
    serde_message.to_string()
}

fn serde_error_column_byte(data: &[u8], message: &str) -> Option<u8> {
    let column = message
        .rsplit_once("column ")?
        .1
        .trim()
        .parse::<usize>()
        .ok()?;
    data.get(column.saturating_sub(1)).copied()
}

fn read_nonempty_line<R: BufRead>(reader: &mut R) -> Result<Option<(String, usize)>, String> {
    let mut total_bytes = 0;
    loop {
        match read_limited_line(reader, MAX_LINE_BYTES)? {
            Some(line) if !line.trim().is_empty() => {
                total_bytes += line.len();
                return Ok(Some((line, total_bytes)));
            }
            Some(line) => {
                total_bytes += line.len();
            }
            None => return Ok(None),
        }
    }
}

fn read_limited_line<R: BufRead>(reader: &mut R, limit: usize) -> Result<Option<String>, String> {
    let mut output = Vec::new();
    loop {
        let available = reader.fill_buf().map_err(|error| error.to_string())?;
        if available.is_empty() {
            return if output.is_empty() {
                Ok(None)
            } else {
                Ok(Some(String::from_utf8_lossy(&output).into_owned()))
            };
        }
        let take = available
            .iter()
            .position(|byte| *byte == b'\n')
            .map_or(available.len(), |position| position + 1);
        if output.len() + take > limit {
            return Err(format!("line exceeds {limit} bytes"));
        }
        let has_newline = available[..take].contains(&b'\n');
        output.extend_from_slice(&available[..take]);
        reader.consume(take);
        if has_newline {
            return Ok(Some(String::from_utf8_lossy(&output).into_owned()));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use schemars::JsonSchema;
    use serde::Deserialize;
    use std::io::Cursor;
    use std::sync::atomic::AtomicUsize;
    use std::time::Duration;

    fn line(request: &str) -> Vec<u8> {
        format!("{request}\n").into_bytes()
    }

    #[derive(Clone)]
    struct Capture(Arc<Mutex<Vec<u8>>>);

    struct BlockingReader(std::sync::mpsc::Receiver<()>);

    impl Read for BlockingReader {
        fn read(&mut self, _bytes: &mut [u8]) -> io::Result<usize> {
            self.0
                .recv()
                .map(|_| 0)
                .map_err(|error| io::Error::other(error.to_string()))
        }
    }

    struct FailingWriter;

    impl Write for FailingWriter {
        fn write(&mut self, _bytes: &[u8]) -> io::Result<usize> {
            Err(io::Error::new(io::ErrorKind::BrokenPipe, "closed"))
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl Write for Capture {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    fn run(server: &Server, input: Vec<u8>) -> Vec<u8> {
        let bytes = Arc::new(Mutex::new(Vec::new()));
        server
            .serve_io(Cursor::new(input), Capture(Arc::clone(&bytes)))
            .unwrap();
        bytes.lock().unwrap().clone()
    }

    fn frame(request: &str) -> Vec<u8> {
        format!("Content-Length: {}\r\n\r\n{request}", request.len()).into_bytes()
    }

    #[test]
    fn line_and_content_length_modes_preserve_large_numeric_id() {
        for bytes in [
            line(r#"{"jsonrpc":"2.0","id":9007199254740993,"method":"ping"}"#),
            frame(r#"{"jsonrpc":"2.0","id":9007199254740993,"method":"ping"}"#),
        ] {
            let server = Server::new("test", "1.0");
            let output = run(&server, bytes);
            assert!(
                String::from_utf8(output)
                    .unwrap()
                    .contains("9007199254740993")
            );
        }
    }

    #[test]
    fn notifications_execute_without_output() {
        let calls = Arc::new(AtomicUsize::new(0));
        let server = Server::new("test", "1.0");
        let seen = Arc::clone(&calls);
        server
            .register_tool(Tool::new("write", "write").handler(move |_, _| {
                seen.fetch_add(1, Ordering::SeqCst);
                Ok(ToolOutput::from("written"))
            }))
            .unwrap();
        let input = line(
            r#"{"jsonrpc":"2.0","method":"tools/call","params":{"name":"write","arguments":{}}}"#,
        );
        let output = run(&server, input);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert!(output.is_empty());
    }

    #[test]
    fn eof_waits_for_concurrent_call() {
        let server = Server::new("test", "1.0");
        let started = Arc::new(AtomicBool::new(false));
        let seen = Arc::clone(&started);
        server
            .register_tool(Tool::new("wait", "wait").handler(move |_, _| {
                seen.store(true, Ordering::Release);
                thread::sleep(Duration::from_millis(10));
                Ok(ToolOutput::from("done"))
            }))
            .unwrap();
        let input = line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"wait","arguments":{}}}"#,
        );
        let output = run(&server, input);
        assert!(started.load(Ordering::Acquire));
        assert!(String::from_utf8(output).unwrap().contains("done"));
    }

    #[test]
    fn framing_is_bounded_before_body_allocation() {
        let mut input = vec![b'a'; MAX_LINE_BYTES + 1];
        input.push(b'\n');
        let error = Server::new("test", "1.0")
            .serve_io(Cursor::new(input), Vec::new())
            .unwrap_err();
        assert!(error.to_string().contains("exceeds"));
    }

    #[test]
    fn frame_parser_fuzz_smoke_10000() {
        let mut state = 0x9e37_79b9_u64;
        for _ in 0..10_000 {
            state = state
                .wrapping_mul(6_364_136_223_846_793_005)
                .wrapping_add(1);
            let length = (state as usize) % 2_048;
            let mut bytes = Vec::with_capacity(length + 1);
            for _ in 0..length {
                state = state.rotate_left(7) ^ 0xa5a5_a5a5_a5a5_a5a5;
                bytes.push(state as u8);
            }
            bytes.push(b'\n');
            let mut reader = BufReader::new(Cursor::new(bytes));
            let _ = read_request(&mut reader);
        }
    }

    #[test]
    fn typed_registration_rejects_unknown_fields() {
        #[derive(Deserialize, JsonSchema)]
        struct Args {
            query: String,
        }
        let server = Server::new("test", "1.0");
        server
            .register_typed::<Args, _>("search", "search", |_, args| {
                Ok(ToolOutput::from(args.query))
            })
            .unwrap();
        let input = line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"x","extra":1}}}"#,
        );
        let output = run(&server, input);
        assert!(String::from_utf8(output).unwrap().contains("isError"));
    }

    #[test]
    fn typed_registration_derives_nested_arrays_options_tags_and_descriptions() {
        #[derive(Deserialize, JsonSchema)]
        struct Nested {
            #[serde(rename = "label")]
            #[schemars(description = "nested label")]
            label: String,
        }
        #[derive(Deserialize, JsonSchema)]
        struct Rich {
            #[serde(rename = "items")]
            items: Vec<Nested>,
            #[serde(rename = "optional", default)]
            optional: Option<String>,
        }
        let server = Server::new("test", "1.0");
        server
            .register_typed::<Rich, _>("rich", "rich", |_, input| {
                Ok(ToolOutput::from(format!(
                    "{}:{}:{}",
                    input.items.len(),
                    input.optional.unwrap_or_default(),
                    input
                        .items
                        .iter()
                        .map(|item| item.label.len())
                        .sum::<usize>()
                )))
            })
            .unwrap();
        let response: Value = serde_json::from_slice(&run(
            &server,
            line(r#"{"jsonrpc":"2.0","id":1,"method":"tools/list"}"#),
        ))
        .unwrap();
        let schema = &response["result"]["tools"][0]["inputSchema"];
        assert_eq!(schema["type"], "object");
        assert_eq!(schema["properties"]["items"]["type"], "array");
        assert!(schema["properties"]["items"]["items"].is_object());
        assert!(schema["properties"]["optional"].is_object());
        assert!(
            !schema["required"]
                .as_array()
                .unwrap()
                .iter()
                .any(|name| name == "optional")
        );
        let schema_text = serde_json::to_string(schema).unwrap();
        assert!(schema_text.contains("nested label"));
        assert!(
            server
                .register_typed::<Vec<String>, _>("bad", "bad", |_, _| {
                    Ok(ToolOutput::from("unreachable"))
                })
                .is_err()
        );
    }

    #[test]
    fn concurrent_tool_calls_are_bounded_by_the_limiter() {
        let active = Arc::new(AtomicUsize::new(0));
        let maximum = Arc::new(AtomicUsize::new(0));
        let server = Server::new("test", "1.0");
        let active_for_handler = Arc::clone(&active);
        let maximum_for_handler = Arc::clone(&maximum);
        server
            .register_tool(Tool::new("bounded", "bounded").handler(move |_, _| {
                let now = active_for_handler.fetch_add(1, Ordering::SeqCst) + 1;
                maximum_for_handler.fetch_max(now, Ordering::SeqCst);
                thread::sleep(Duration::from_millis(2));
                active_for_handler.fetch_sub(1, Ordering::SeqCst);
                Ok(ToolOutput::from("ok"))
            }))
            .unwrap();
        let input = (0..64)
            .map(|id| format!(r#"{{"jsonrpc":"2.0","id":{id},"method":"tools/call","params":{{"name":"bounded","arguments":{{}}}}}}"#) + "\n")
            .collect::<String>();
        let output = run(&server, input.into_bytes());
        assert_eq!(output.iter().filter(|byte| **byte == b'\n').count(), 64);
        assert!(maximum.load(Ordering::SeqCst) <= MAX_CONCURRENT_TOOL_CALLS);
    }

    #[test]
    fn cancellation_returns_without_joining_a_blocking_reader() {
        let (release, blocked) = std::sync::mpsc::channel();
        let token = CancellationToken::new();
        let worker_token = token.clone();
        let server = Server::new("test", "1.0");
        let worker = thread::spawn(move || {
            server.serve_io_cancellable(BlockingReader(blocked), Vec::new(), worker_token)
        });
        thread::sleep(Duration::from_millis(20));
        token.cancel();
        assert_eq!(worker.join().unwrap(), Err(TransportError::Cancelled));
        let _ = release.send(());
    }

    #[test]
    fn write_failure_is_returned_instead_of_becoming_cancellation() {
        let server = Server::new("test", "1.0");
        server
            .register_tool(
                Tool::new("write", "write").handler(|_, _| Ok(ToolOutput::from("written"))),
            )
            .unwrap();
        let input = line(
            r#"{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"write","arguments":{}}}"#,
        );
        assert!(matches!(
            server.serve_io(Cursor::new(input), FailingWriter),
            Err(TransportError::Write(_))
        ));
    }
}
