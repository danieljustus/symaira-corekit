use crate::client::{Client, read_limited};
use crate::error::{Error, ErrorCode, Result};
use crate::provider::WireDialect;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

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
        let parsed: OpenAiResponse = serde_json::from_slice(&raw).map_err(|e| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode chat response: {e}"),
            )
        })?;
        let Some(choice) = parsed.choices.into_iter().next() else {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: chat response contained no choices",
            ));
        };
        let calls = choice
            .message
            .tool_calls
            .into_iter()
            .map(|call| ToolCall {
                id: call.id,
                name: call.function.name,
                arguments: serde_json::from_str(&call.function.arguments)
                    .unwrap_or(Value::String(call.function.arguments)),
            })
            .collect();
        Ok(Choice {
            content: choice.message.content.unwrap_or_default(),
            tool_calls: calls,
            finish_reason: choice.finish_reason.unwrap_or_default(),
        })
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
        let content = parsed
            .content
            .into_iter()
            .filter(|part| part.kind.as_deref().unwrap_or("text") == "text")
            .map(|part| part.text)
            .collect();
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
        let reader = BufReader::new(response.body_mut().as_reader());
        let mut reader = reader;
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
                        format!("llmkit: decode stream chunk: {e}"),
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
                "stream line exceeds 1 MiB",
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

fn refine_openai_error(mut error: Error) -> Error {
    if error.status_code == 0 || error.body.is_empty() {
        return error;
    }
    let Ok(value) = serde_json::from_str::<Value>(&error.body) else {
        return error;
    };
    let message = value
        .pointer("/error/message")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let kind = value
        .pointer("/error/type")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_ascii_lowercase();
    let text = format!("{kind} {message}");
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

#[derive(Deserialize)]
struct OpenAiResponse {
    #[serde(default)]
    choices: Vec<OpenAiChoice>,
}
#[derive(Deserialize)]
struct OpenAiChoice {
    message: OpenAiMessage,
    finish_reason: Option<String>,
}
#[derive(Deserialize)]
struct OpenAiMessage {
    content: Option<String>,
    #[serde(default)]
    tool_calls: Vec<OpenAiToolCall>,
}
#[derive(Deserialize)]
struct OpenAiToolCall {
    id: String,
    function: OpenAiFunction,
}
#[derive(Deserialize)]
struct OpenAiFunction {
    name: String,
    arguments: String,
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
    #[serde(rename = "type")]
    kind: Option<String>,
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
