use crate::client::{Client, cancel_on, read_limited, read_reqwest_limited};
use crate::error::{Error, ErrorCode, Result};
use crate::provider::WireDialect;
use serde::de::{DeserializeSeed, IgnoredAny, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::value::RawValue;
use serde_json::{Value, json};
use std::fmt;
use tokio_util::sync::CancellationToken;

#[derive(Clone, Debug, Default, Deserialize, Serialize, Eq, PartialEq)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(Clone, Debug)]
pub struct Tool {
    pub name: String,
    pub description: String,
    pub parameters: Value,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct ToolCall {
    pub id: String,
    pub name: String,
    pub arguments: Value,
}

#[derive(Clone, Debug, Default)]
pub struct ChatOptions {
    pub temperature: Option<f64>,
    pub max_tokens: u32,
    pub system: String,
    pub tools: Vec<Tool>,
    pub response_format: Option<Value>,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct Choice {
    pub content: String,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub tool_calls: Vec<ToolCall>,
    #[serde(skip_serializing_if = "String::is_empty")]
    pub finish_reason: String,
}

impl Client {
    pub fn chat(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        if model.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: model is required for provider {:?}",
                    self.descriptor().id
                ),
            ));
        }
        if messages.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: messages must not be empty",
            ));
        }
        match self.dialect {
            WireDialect::Openai => self.chat_openai(model, messages, options),
            WireDialect::Anthropic => self.chat_anthropic(model, messages, options),
        }
    }

    /// Performs chat over the cancellable async transport.
    ///
    /// Cancelling `token` drops the in-flight request or response read and
    /// closes its connection. Use [`ClientBuilder::async_client`] to configure
    /// this transport. A blocking `ureq::Agent` alone cannot be interrupted.
    pub async fn chat_cancellable(
        &self,
        token: &CancellationToken,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        cancel_on(token, self.chat_cancellable_inner(model, messages, options)).await
    }

    async fn chat_cancellable_inner(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        if model.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: model is required for provider {:?}",
                    self.descriptor().id
                ),
            ));
        }
        if messages.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: messages must not be empty",
            ));
        }
        match self.dialect {
            WireDialect::Openai => self.chat_openai_cancellable(model, messages, options).await,
            WireDialect::Anthropic => {
                self.chat_anthropic_cancellable(model, messages, options)
                    .await
            }
        }
    }

    async fn chat_openai_cancellable(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let opts = options.cloned().unwrap_or_default();
        if !opts.tools.is_empty() && !self.descriptor().capabilities.tool_use {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not promise tool_use",
                    self.descriptor().id
                ),
            ));
        }
        let mut converted = Vec::new();
        if !opts.system.is_empty() {
            converted.push(json!({"role":"system","content":opts.system}));
        }
        converted.extend(
            messages
                .iter()
                .map(|message| json!({"role":message.role,"content":message.content})),
        );
        let mut body = json!({"model":model,"messages":converted,"stream":false});
        if let Some(temperature) = opts.temperature {
            body["temperature"] = json!(temperature);
        }
        if opts.max_tokens != 0 {
            body["max_tokens"] = json!(opts.max_tokens);
        }
        let tools: Vec<Value> = opts.tools.iter().map(openai_tool).collect();
        if !tools.is_empty() {
            body["tools"] = json!(tools);
        }
        if let Some(format) = opts.response_format {
            body["response_format"] = format;
        }
        let mut response = match self
            .request_cancellable(reqwest::Method::POST, "/chat/completions", Some(&body))
            .await
        {
            Ok(response) => response,
            Err(error) => return Err(refine_openai_error(error)),
        };
        let raw = read_reqwest_limited(&mut response, 16 << 20).await?;
        decode_openai_response(&raw)
    }

    async fn chat_anthropic_cancellable(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let opts = options.cloned().unwrap_or_default();
        let body = anthropic_body(model, messages, &opts);
        let mut response = self
            .request_cancellable(reqwest::Method::POST, "/messages", Some(&body))
            .await
            .map_err(refine_anthropic_error)?;
        let raw = read_reqwest_limited(&mut response, 16 << 20).await?;
        let parsed: AnthropicResponse = serde_json::from_slice(&raw).map_err(|error| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode anthropic response: {error}"),
            )
        })?;
        Ok(Choice {
            content: parsed.content.into_iter().map(|part| part.text).collect(),
            tool_calls: Vec::new(),
            finish_reason: parsed.stop_reason.unwrap_or_default(),
        })
    }

    fn chat_openai(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let mut converted = Vec::new();
        if let Some(system) = options.filter(|o| !o.system.is_empty()) {
            converted.push(json!({"role":"system","content":system.system}));
        }
        converted.extend(
            messages
                .iter()
                .map(|m| json!({"role":m.role,"content":m.content})),
        );
        let opts = options.cloned().unwrap_or_default();
        if !opts.tools.is_empty() && !self.descriptor().capabilities.tool_use {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not promise tool_use",
                    self.descriptor().id
                ),
            ));
        }
        let tools: Vec<Value> = opts.tools.iter().map(openai_tool).collect();
        let mut body = json!({"model":model,"messages":converted,"stream":false});
        if let Some(value) = opts.temperature {
            body["temperature"] = json!(value);
        }
        if opts.max_tokens != 0 {
            body["max_tokens"] = json!(opts.max_tokens);
        }
        if !tools.is_empty() {
            body["tools"] = json!(tools);
        }
        if let Some(format) = opts.response_format {
            body["response_format"] = format;
        }
        let mut response = match self.request("POST", "/chat/completions", Some(&body)) {
            Ok(response) => response,
            Err(error) => return Err(refine_openai_error(error)),
        };
        let raw = read_limited(&mut response, 16 << 20)?;
        decode_openai_response(&raw)
    }

    fn chat_anthropic(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
    ) -> Result<Choice> {
        let opts = options.cloned().unwrap_or_default();
        let mut system = opts.system;
        let mut converted = Vec::new();
        for message in messages {
            if message.role == "system" {
                if system.is_empty() {
                    system.clone_from(&message.content);
                } else {
                    system.push_str("\n\n");
                    system.push_str(&message.content);
                }
            } else {
                converted.push(json!({"role":message.role,"content":message.content}));
            }
        }
        let tools: Vec<Value> = opts.tools.iter().map(anthropic_tool).collect();
        let mut body = json!({"model":model,"max_tokens":if opts.max_tokens == 0 { 8192 } else { opts.max_tokens },"messages":converted});
        if !system.is_empty() {
            body["system"] = json!(system);
        }
        if !tools.is_empty() {
            body["tools"] = json!(tools);
        }
        let mut response = match self.request("POST", "/messages", Some(&body)) {
            Ok(response) => response,
            Err(error) => return Err(refine_anthropic_error(error)),
        };
        let raw = read_limited(&mut response, 16 << 20)?;
        let parsed: AnthropicResponse = serde_json::from_slice(&raw).map_err(|e| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode anthropic response: {e}"),
            )
        })?;
        let content = parsed.content.into_iter().map(|part| part.text).collect();
        Ok(Choice {
            content,
            tool_calls: Vec::new(),
            finish_reason: parsed.stop_reason.unwrap_or_default(),
        })
    }

    pub fn stream_chat<F, G>(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
        mut callback: F,
        mut on_finish: G,
    ) -> Result<()>
    where
        F: FnMut(&str) -> Result<()>,
        G: FnMut(&str),
    {
        if !self.descriptor().capabilities.streaming {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not promise streaming",
                    self.descriptor().id
                ),
            ));
        }
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        if model.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: model is required for provider {:?}",
                    self.descriptor().id
                ),
            ));
        }
        let opts = options.cloned().unwrap_or_default();
        let mut body = if self.dialect == WireDialect::Anthropic {
            anthropic_body(model, messages, &opts)
        } else {
            let mut converted = Vec::new();
            if !opts.system.is_empty() {
                converted.push(json!({"role":"system","content":opts.system}));
            }
            converted.extend(
                messages
                    .iter()
                    .map(|m| json!({"role":m.role,"content":m.content})),
            );
            let mut body = json!({"model":model,"messages":converted,"stream":true});
            if let Some(temperature) = opts.temperature {
                body["temperature"] = json!(temperature);
            }
            if opts.max_tokens != 0 {
                body["max_tokens"] = json!(opts.max_tokens);
            }
            body
        };
        body["stream"] = json!(true);
        let path = if self.dialect == WireDialect::Anthropic {
            "/messages"
        } else {
            "/chat/completions"
        };
        let mut response = self.request("POST", path, Some(&body))?;
        use std::io::BufReader;
        let mut reader = BufReader::new(&mut response);
        let mut started = false;
        while let Some(raw_line) = read_bounded_line(&mut reader, 1024 * 1024).map_err(|e| {
            Error::transport(if started {
                format!("stream interrupted: {e}")
            } else {
                e.to_string()
            })
        })? {
            let line = String::from_utf8_lossy(&raw_line);
            let Some(data) = line.strip_prefix("data:") else {
                continue;
            };
            let data = data.trim();
            if data.is_empty() || data == "[DONE]" {
                continue;
            }
            started = true;
            if self.dialect == WireDialect::Openai {
                let chunk: OpenAiChunk = serde_json::from_str(data).map_err(|e| {
                    Error::local(
                        ErrorCode::ProviderError,
                        format!(
                            "llmkit: decode stream chunk: {}",
                            crate::ollama::go_json_error(data.as_bytes(), &e)
                        ),
                    )
                })?;
                if let Some(choice) = chunk.choices.first() {
                    if let Some(reason) = choice.finish_reason.as_deref().filter(|s| !s.is_empty())
                    {
                        on_finish(reason);
                    }
                    if !choice.delta.content.is_empty() {
                        callback(&choice.delta.content)?;
                    }
                }
            } else if let Ok(event) = serde_json::from_str::<AnthropicEvent>(data) {
                if event.kind == "message_delta" {
                    if let Some(reason) = event
                        .delta
                        .and_then(|d| d.stop_reason)
                        .filter(|s| !s.is_empty())
                    {
                        on_finish(&reason);
                    }
                } else if event.kind == "content_block_delta"
                    && let Some(text) = event.delta.and_then(|d| d.text).filter(|s| !s.is_empty())
                {
                    callback(&text)?;
                }
            }
        }
        if !started {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: no stream data received",
            ));
        }
        Ok(())
    }

    /// Streams chat over the cancellable async transport.
    ///
    /// Cancelling `token` drops the active response read and closes its
    /// connection. Use [`ClientBuilder::async_client`] to configure this
    /// transport. A blocking `ureq::Agent` alone cannot be interrupted.
    pub async fn stream_chat_cancellable<F, G>(
        &self,
        token: &CancellationToken,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
        mut callback: F,
        mut on_finish: G,
    ) -> Result<()>
    where
        F: FnMut(&str) -> Result<()>,
        G: FnMut(&str),
    {
        cancel_on(
            token,
            self.stream_chat_cancellable_inner(
                model,
                messages,
                options,
                &mut callback,
                &mut on_finish,
            ),
        )
        .await
    }

    async fn stream_chat_cancellable_inner<F, G>(
        &self,
        model: &str,
        messages: &[Message],
        options: Option<&ChatOptions>,
        callback: &mut F,
        on_finish: &mut G,
    ) -> Result<()>
    where
        F: FnMut(&str) -> Result<()>,
        G: FnMut(&str),
    {
        if !self.descriptor().capabilities.streaming {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not promise streaming",
                    self.descriptor().id
                ),
            ));
        }
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        if model.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: model is required for provider {:?}",
                    self.descriptor().id
                ),
            ));
        }
        let opts = options.cloned().unwrap_or_default();
        let mut body = if self.dialect == WireDialect::Anthropic {
            anthropic_body(model, messages, &opts)
        } else {
            let mut converted = Vec::new();
            if !opts.system.is_empty() {
                converted.push(json!({"role":"system","content":opts.system}));
            }
            converted.extend(
                messages
                    .iter()
                    .map(|message| json!({"role":message.role,"content":message.content})),
            );
            let mut body = json!({"model":model,"messages":converted,"stream":true});
            if let Some(temperature) = opts.temperature {
                body["temperature"] = json!(temperature);
            }
            if opts.max_tokens != 0 {
                body["max_tokens"] = json!(opts.max_tokens);
            }
            body
        };
        body["stream"] = json!(true);
        let path = if self.dialect == WireDialect::Anthropic {
            "/messages"
        } else {
            "/chat/completions"
        };
        let mut response = self
            .request_cancellable(reqwest::Method::POST, path, Some(&body))
            .await?;
        let mut pending = Vec::new();
        let mut started = false;
        while let Some(chunk) = response.chunk().await.map_err(|error| {
            Error::transport(if started {
                format!("llmkit: stream interrupted: {}", error.without_url())
            } else {
                error.without_url().to_string()
            })
        })? {
            pending.extend_from_slice(&chunk);
            while let Some(index) = pending.iter().position(|byte| *byte == b'\n') {
                if index + 1 > 1024 * 1024 {
                    return Err(Error::transport(if started {
                        "llmkit: stream interrupted: bufio.Scanner: token too long"
                    } else {
                        "llmkit: bufio.Scanner: token too long"
                    }));
                }
                let line: Vec<u8> = pending.drain(..=index).collect();
                process_cancellable_stream_line(
                    self.dialect,
                    &line,
                    &mut started,
                    callback,
                    on_finish,
                )?;
            }
            if pending.len() > 1024 * 1024 {
                return Err(Error::transport(if started {
                    "llmkit: stream interrupted: bufio.Scanner: token too long"
                } else {
                    "llmkit: bufio.Scanner: token too long"
                }));
            }
        }
        if !pending.is_empty() {
            process_cancellable_stream_line(
                self.dialect,
                &pending,
                &mut started,
                callback,
                on_finish,
            )?;
        }
        if !started {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: no stream data received",
            ));
        }
        Ok(())
    }
}

fn process_cancellable_stream_line<F, G>(
    dialect: WireDialect,
    raw_line: &[u8],
    started: &mut bool,
    callback: &mut F,
    on_finish: &mut G,
) -> Result<()>
where
    F: FnMut(&str) -> Result<()>,
    G: FnMut(&str),
{
    let line = String::from_utf8_lossy(raw_line);
    let Some(data) = line.strip_prefix("data:") else {
        return Ok(());
    };
    let data = data.trim();
    if data.is_empty() || data == "[DONE]" {
        return Ok(());
    }
    *started = true;
    if dialect == WireDialect::Openai {
        let chunk: OpenAiChunk = serde_json::from_str(data).map_err(|error| {
            Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: decode stream chunk: {}",
                    crate::ollama::go_json_error(data.as_bytes(), &error)
                ),
            )
        })?;
        if let Some(choice) = chunk.choices.first() {
            if let Some(reason) = choice.finish_reason.as_deref().filter(|s| !s.is_empty()) {
                on_finish(reason);
            }
            if !choice.delta.content.is_empty() {
                callback(&choice.delta.content)?;
            }
        }
    } else if let Ok(event) = serde_json::from_str::<AnthropicEvent>(data) {
        if event.kind == "message_delta" {
            if let Some(reason) = event
                .delta
                .and_then(|delta| delta.stop_reason)
                .filter(|reason| !reason.is_empty())
            {
                on_finish(&reason);
            }
        } else if event.kind == "content_block_delta"
            && let Some(text) = event
                .delta
                .and_then(|delta| delta.text)
                .filter(|text| !text.is_empty())
        {
            callback(&text)?;
        }
    }
    Ok(())
}

pub(crate) fn read_bounded_line<R: std::io::BufRead>(
    reader: &mut R,
    max: usize,
) -> std::io::Result<Option<Vec<u8>>> {
    use std::io::{Error, ErrorKind};
    let mut line = Vec::new();
    loop {
        let buffer = reader.fill_buf()?;
        if buffer.is_empty() {
            return if line.is_empty() {
                Ok(None)
            } else {
                Ok(Some(line))
            };
        }
        let newline = buffer.iter().position(|byte| *byte == b'\n');
        let count = newline.map_or(buffer.len(), |index| index + 1);
        if line.len() + count > max {
            return Err(Error::new(
                ErrorKind::InvalidData,
                "bufio.Scanner: token too long",
            ));
        }
        line.extend_from_slice(&buffer[..count]);
        reader.consume(count);
        if newline.is_some() {
            return Ok(Some(line));
        }
    }
}

fn anthropic_body(model: &str, messages: &[Message], options: &ChatOptions) -> Value {
    let mut system = options.system.clone();
    let mut converted = Vec::new();
    for message in messages {
        if message.role == "system" {
            if system.is_empty() {
                system.clone_from(&message.content);
            } else {
                system.push_str("\n\n");
                system.push_str(&message.content);
            }
        } else {
            converted.push(json!({"role":message.role,"content":message.content}));
        }
    }
    let mut body = json!({"model":model,"max_tokens":if options.max_tokens == 0 { 8192 } else { options.max_tokens },"messages":converted});
    if !system.is_empty() {
        body["system"] = json!(system);
    }
    if !options.tools.is_empty() {
        body["tools"] = json!(options.tools.iter().map(anthropic_tool).collect::<Vec<_>>());
    }
    body
}

fn openai_tool(tool: &Tool) -> Value {
    let mut function = serde_json::Map::new();
    function.insert("name".into(), json!(tool.name));
    if !tool.description.is_empty() {
        function.insert("description".into(), json!(tool.description));
    }
    if !tool.parameters.is_null() {
        function.insert("parameters".into(), tool.parameters.clone());
    }
    json!({"type":"function","function":function})
}

fn anthropic_tool(tool: &Tool) -> Value {
    let mut value = serde_json::Map::new();
    value.insert("name".into(), json!(tool.name));
    if !tool.description.is_empty() {
        value.insert("description".into(), json!(tool.description));
    }
    if !tool.parameters.is_null() {
        value.insert("input_schema".into(), tool.parameters.clone());
    }
    Value::Object(value)
}

fn refine_anthropic_error(mut error: Error) -> Error {
    if error.status_code == 0 {
        return error;
    }
    let mut text = error.body.to_ascii_lowercase();
    if let Ok(value) = serde_json::from_str::<Value>(&error.body) {
        if let Some(message) = value.pointer("/error/message").and_then(Value::as_str) {
            text.push(' ');
            text.push_str(&message.to_ascii_lowercase());
        }
        if let Some(kind) = value.pointer("/error/type").and_then(Value::as_str) {
            text.push(' ');
            text.push_str(&kind.to_ascii_lowercase());
        }
    }
    if ["authentication", "invalid api key", "permission"]
        .iter()
        .any(|m| text.contains(m))
    {
        error.code = ErrorCode::AuthFailure;
    } else if ["rate limit", "overloaded"]
        .iter()
        .any(|m| text.contains(m))
    {
        error.code = ErrorCode::RateLimited;
    } else if ["not_found", "no such model"]
        .iter()
        .any(|m| text.contains(m))
    {
        error.code = ErrorCode::ModelNotFound;
    }
    error
}

fn refine_openai_error(error: Error) -> Error {
    if error.status_code == 0 || error.body.is_empty() {
        return error;
    }
    let Ok(envelope) = serde_json::from_str::<OpenAiErrorEnvelope>(&error.body) else {
        return error;
    };
    let Some(typed) = envelope.error else {
        return error;
    };
    let mut refined = Error::http(400, typed.message.as_bytes(), "");
    let text = format!("{} {}", typed.kind, typed.message).to_lowercase();
    if ["authentication", "invalid api key", "permission"]
        .iter()
        .any(|m| text.contains(m))
    {
        refined.code = ErrorCode::AuthFailure;
    } else if ["rate limit", "overloaded"]
        .iter()
        .any(|m| text.contains(m))
    {
        refined.code = ErrorCode::RateLimited;
    } else if ["not_found", "no such model"]
        .iter()
        .any(|m| text.contains(m))
    {
        refined.code = ErrorCode::ModelNotFound;
    }
    if refined.code == ErrorCode::ProviderError {
        error
    } else {
        refined
    }
}

struct OpenAiErrorEnvelope {
    error: Option<OpenAiTypedError>,
}

struct OpenAiTypedError {
    message: String,
    kind: String,
}

impl<'de> Deserialize<'de> for OpenAiErrorEnvelope {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct EnvelopeVisitor;

        impl<'de> Visitor<'de> for EnvelopeVisitor {
            type Value = OpenAiErrorEnvelope;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an OpenAI error response object")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut error = None;
                while let Some(key) = map.next_key::<String>()? {
                    if key.eq_ignore_ascii_case("choices") {
                        let _: Option<Vec<GoOpenAiChoice>> = map.next_value()?;
                    } else if key.eq_ignore_ascii_case("error") {
                        error = map.next_value::<Option<OpenAiTypedError>>()?;
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(OpenAiErrorEnvelope { error })
            }
        }

        deserializer.deserialize_map(EnvelopeVisitor)
    }
}

impl<'de> Deserialize<'de> for OpenAiTypedError {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct OpenAiErrorVisitor;

        impl<'de> Visitor<'de> for OpenAiErrorVisitor {
            type Value = OpenAiTypedError;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an OpenAI error object")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut message = String::new();
                let mut kind = String::new();
                while let Some(key) = map.next_key::<String>()? {
                    let target = if key.eq_ignore_ascii_case("message") {
                        Some(&mut message)
                    } else if key.eq_ignore_ascii_case("type") {
                        Some(&mut kind)
                    } else {
                        None
                    };
                    if let Some(target) = target {
                        if let Some(value) = map.next_value::<Option<String>>()? {
                            *target = value;
                        }
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(OpenAiTypedError { message, kind })
            }
        }

        deserializer.deserialize_map(OpenAiErrorVisitor)
    }
}

macro_rules! go_json_struct_validator {
    ($type_name:ident, $visitor_name:ident, $expecting:literal, { $($field:literal => $field_type:ty),* $(,)? }) => {
        struct $type_name;

        impl<'de> Deserialize<'de> for $type_name {
            fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                struct $visitor_name;

                impl<'de> Visitor<'de> for $visitor_name {
                    type Value = $type_name;

                    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                        formatter.write_str($expecting)
                    }

                    fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
                    where
                        E: serde::de::Error,
                    {
                        Ok($type_name)
                    }

                    fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
                    where
                        M: MapAccess<'de>,
                    {
                        while let Some(key) = map.next_key::<String>()? {
                            match key.to_ascii_lowercase().as_str() {
                                $($field => {
                                    let _: $field_type = map.next_value()?;
                                },)*
                                _ => {
                                    let _: IgnoredAny = map.next_value()?;
                                }
                            }
                        }
                        Ok($type_name)
                    }
                }

                deserializer.deserialize_any($visitor_name)
            }
        }
    };
}

go_json_struct_validator!(
    GoOpenAiChoice,
    GoOpenAiChoiceVisitor,
    "an OpenAI choice object",
    {
        "message" => GoOpenAiMessage,
        "finish_reason" => Option<String>,
    }
);

go_json_struct_validator!(
    GoOpenAiMessage,
    GoOpenAiMessageVisitor,
    "an OpenAI message object",
    {
        "content" => Option<String>,
        "tool_calls" => Option<Vec<GoOpenAiToolCall>>,
    }
);

go_json_struct_validator!(
    GoOpenAiToolCall,
    GoOpenAiToolCallVisitor,
    "an OpenAI tool call object",
    {
        "id" => Option<String>,
        "type" => Option<String>,
        "function" => GoOpenAiFunction,
    }
);

go_json_struct_validator!(
    GoOpenAiFunction,
    GoOpenAiFunctionVisitor,
    "an OpenAI function object",
    {
        "name" => Option<String>,
        "arguments" => Option<String>,
    }
);

fn decode_openai_response(raw: &[u8]) -> Result<Choice> {
    let parsed: OpenAiResponse = serde_json::from_slice(raw).map_err(|error| {
        Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: decode chat response: {error}"),
        )
    })?;
    let Some(choice) = parsed.choices.into_active().into_iter().next() else {
        return Err(Error::local(
            ErrorCode::ProviderError,
            "llmkit: chat response contained no choices",
        ));
    };
    let tool_calls = choice
        .message
        .tool_calls
        .into_active()
        .into_iter()
        .map(|call| {
            let arguments = call.function.arguments;
            ToolCall {
                id: call.id,
                name: call.function.name,
                arguments: serde_json::from_str(&arguments).unwrap_or(Value::String(arguments)),
            }
        })
        .collect();
    Ok(Choice {
        content: choice.message.content,
        tool_calls,
        finish_reason: choice.finish_reason,
    })
}

fn go_field_eq(key: &str, field: &str) -> bool {
    key.chars()
        .map(|character| match character {
            'A'..='Z' => character.to_ascii_lowercase(),
            '\u{017f}' => 's', // Unicode long s is folded to ASCII S by Go.
            '\u{212a}' => 'k', // Kelvin sign is folded to ASCII K by Go.
            other => other,
        })
        .eq(field.chars())
}

struct OpenAiSuccessError;

impl<'de> Deserialize<'de> for OpenAiSuccessError {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct SuccessErrorVisitor;

        impl<'de> Visitor<'de> for SuccessErrorVisitor {
            type Value = OpenAiSuccessError;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an OpenAI error object")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                while let Some(key) = map.next_key::<String>()? {
                    if go_field_eq(&key, "message") || go_field_eq(&key, "type") {
                        let _: Option<String> = map.next_value()?;
                    } else if go_field_eq(&key, "code") {
                        let code: Option<Box<RawValue>> = map.next_value()?;
                        if let Some(code) = code {
                            validate_openai_any_number_ranges(code.get())
                                .map_err(serde::de::Error::custom)?;
                        }
                    } else {
                        // In the Go response type `code` is `any`; unknown
                        // object fields are ignored.
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(OpenAiSuccessError)
            }
        }

        deserializer.deserialize_any(SuccessErrorVisitor)
    }
}

fn validate_openai_any_number_ranges(raw: &str) -> std::result::Result<(), &'static str> {
    let bytes = raw.as_bytes();
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'"' => {
                index += 1;
                while index < bytes.len() {
                    match bytes[index] {
                        b'\\' => index += 2,
                        b'"' => {
                            index += 1;
                            break;
                        }
                        _ => index += 1,
                    }
                }
            }
            b'-' | b'0'..=b'9' => {
                let start = index;
                while index < bytes.len()
                    && matches!(bytes[index], b'0'..=b'9' | b'-' | b'.' | b'e' | b'E' | b'+')
                {
                    index += 1;
                }
                let number = raw[start..index]
                    .parse::<f64>()
                    .map_err(|_| "invalid number in Go interface value")?;
                if !number.is_finite() {
                    return Err("number out of range for Go interface value");
                }
            }
            _ => index += 1,
        }
    }
    Ok(())
}

trait GoObject {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error>;
}

struct GoObjectSeed<'a, T>(&'a mut T);

impl<'de, T: GoObject> DeserializeSeed<'de> for GoObjectSeed<'_, T> {
    type Value = ();

    fn deserialize<D>(self, deserializer: D) -> std::result::Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct ObjectVisitor<'a, T>(&'a mut T);

        impl<'de, T: GoObject> Visitor<'de> for ObjectVisitor<'_, T> {
            type Value = ();

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an OpenAI response object or null")
            }

            fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                // Go leaves non-pointer structs unchanged when a JSON value is null.
                Ok(())
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                while let Some(key) = map.next_key::<String>()? {
                    self.0.read_field(&key, &mut map)?;
                }
                Ok(())
            }
        }

        deserializer.deserialize_any(ObjectVisitor(self.0))
    }
}

struct GoSlice<T> {
    slots: Vec<T>,
    len: usize,
}

impl<T> Default for GoSlice<T> {
    fn default() -> Self {
        Self {
            slots: Vec::new(),
            len: 0,
        }
    }
}

impl<T> GoSlice<T> {
    fn into_active(self) -> Vec<T> {
        self.slots.into_iter().take(self.len).collect()
    }
}

struct GoSliceSeed<'a, T>(&'a mut GoSlice<T>);

impl<'de, T: GoObject + Default> DeserializeSeed<'de> for GoSliceSeed<'_, T> {
    type Value = ();

    fn deserialize<D>(self, deserializer: D) -> std::result::Result<Self::Value, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct SliceVisitor<'a, T>(&'a mut GoSlice<T>);

        impl<'de, T: GoObject + Default> Visitor<'de> for SliceVisitor<'_, T> {
            type Value = ();

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an array or null")
            }

            fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                self.0.slots.clear();
                self.0.len = 0;
                Ok(())
            }

            fn visit_seq<A>(self, mut sequence: A) -> std::result::Result<Self::Value, A::Error>
            where
                A: SeqAccess<'de>,
            {
                let mut len = 0;
                loop {
                    if len < self.0.slots.len() {
                        if sequence
                            .next_element_seed(GoObjectSeed(&mut self.0.slots[len]))?
                            .is_none()
                        {
                            break;
                        }
                    } else {
                        let mut value = T::default();
                        if sequence
                            .next_element_seed(GoObjectSeed(&mut value))?
                            .is_none()
                        {
                            break;
                        }
                        self.0.slots.push(value);
                    }
                    len += 1;
                }
                if len == 0 {
                    // encoding/json replaces a slice with a fresh empty slice for `[]`.
                    self.0.slots.clear();
                }
                self.0.len = len;
                Ok(())
            }
        }

        deserializer.deserialize_any(SliceVisitor(self.0))
    }
}

struct OpenAiResponse {
    choices: GoSlice<OpenAiChoice>,
}

impl<'de> Deserialize<'de> for OpenAiResponse {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct ResponseVisitor;

        impl<'de> Visitor<'de> for ResponseVisitor {
            type Value = OpenAiResponse;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an OpenAI chat response object")
            }

            fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                Ok(OpenAiResponse {
                    choices: GoSlice::default(),
                })
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut response = OpenAiResponse {
                    choices: GoSlice::default(),
                };
                while let Some(key) = map.next_key::<String>()? {
                    response.read_field(&key, &mut map)?;
                }
                Ok(response)
            }
        }

        deserializer.deserialize_any(ResponseVisitor)
    }
}

impl GoObject for OpenAiResponse {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error> {
        if go_field_eq(key, "choices") {
            map.next_value_seed(GoSliceSeed(&mut self.choices))
        } else if go_field_eq(key, "error") {
            // The Go response type validates this pointer's typed fields even
            // though a valid value on HTTP 200 is ignored by Chat.
            let _: Option<OpenAiSuccessError> = map.next_value()?;
            Ok(())
        } else {
            let _: IgnoredAny = map.next_value()?;
            Ok(())
        }
    }
}

#[derive(Default)]
struct OpenAiChoice {
    message: OpenAiMessage,
    finish_reason: String,
}

impl GoObject for OpenAiChoice {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error> {
        if go_field_eq(key, "message") {
            map.next_value_seed(GoObjectSeed(&mut self.message))
        } else if go_field_eq(key, "finish_reason") {
            if let Some(reason) = map.next_value::<Option<String>>()? {
                self.finish_reason = reason;
            }
            Ok(())
        } else {
            let _: IgnoredAny = map.next_value()?;
            Ok(())
        }
    }
}

#[derive(Default)]
struct OpenAiMessage {
    content: String,
    tool_calls: GoSlice<OpenAiToolCall>,
}

impl GoObject for OpenAiMessage {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error> {
        if go_field_eq(key, "content") {
            if let Some(content) = map.next_value::<Option<String>>()? {
                self.content = content;
            }
            Ok(())
        } else if go_field_eq(key, "tool_calls") {
            map.next_value_seed(GoSliceSeed(&mut self.tool_calls))
        } else {
            let _: IgnoredAny = map.next_value()?;
            Ok(())
        }
    }
}

#[derive(Default)]
struct OpenAiToolCall {
    id: String,
    function: OpenAiFunction,
}

impl GoObject for OpenAiToolCall {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error> {
        if go_field_eq(key, "id") {
            if let Some(id) = map.next_value::<Option<String>>()? {
                self.id = id;
            }
            Ok(())
        } else if go_field_eq(key, "type") {
            // The Go struct declares this string even though its converter
            // omits it from the returned ToolCall.
            let _: Option<String> = map.next_value()?;
            Ok(())
        } else if go_field_eq(key, "function") {
            map.next_value_seed(GoObjectSeed(&mut self.function))
        } else {
            let _: IgnoredAny = map.next_value()?;
            Ok(())
        }
    }
}

#[derive(Default)]
struct OpenAiFunction {
    name: String,
    arguments: String,
}

impl GoObject for OpenAiFunction {
    fn read_field<'de, A: MapAccess<'de>>(
        &mut self,
        key: &str,
        map: &mut A,
    ) -> std::result::Result<(), A::Error> {
        if go_field_eq(key, "name") {
            if let Some(name) = map.next_value::<Option<String>>()? {
                self.name = name;
            }
            Ok(())
        } else if go_field_eq(key, "arguments") {
            if let Some(arguments) = map.next_value::<Option<String>>()? {
                self.arguments = arguments;
            }
            Ok(())
        } else {
            let _: IgnoredAny = map.next_value()?;
            Ok(())
        }
    }
}
#[derive(Deserialize)]
struct OpenAiChunk {
    #[serde(default)]
    choices: Vec<OpenAiChunkChoice>,
}
#[derive(Deserialize)]
struct OpenAiChunkChoice {
    delta: OpenAiDelta,
    finish_reason: Option<String>,
}
#[derive(Default, Deserialize)]
struct OpenAiDelta {
    #[serde(default)]
    content: String,
}
#[derive(Deserialize)]
struct AnthropicResponse {
    #[serde(default)]
    content: Vec<AnthropicContent>,
    stop_reason: Option<String>,
}
#[derive(Deserialize)]
struct AnthropicContent {
    #[serde(default)]
    text: String,
}
#[derive(Deserialize)]
struct AnthropicEvent {
    #[serde(rename = "type")]
    kind: String,
    delta: Option<AnthropicDelta>,
}
#[derive(Deserialize)]
struct AnthropicDelta {
    text: Option<String>,
    stop_reason: Option<String>,
}
