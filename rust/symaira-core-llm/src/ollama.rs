use crate::chat::{Message, read_bounded_line};
use crate::client::{Client, cancel_on, read_limited, read_reqwest_limited};
use crate::error::{Error, ErrorCode, Result};
use serde::Deserializer;
use serde::de::{DeserializeOwned, IgnoredAny, MapAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::fmt;
use std::io::BufReader;
use std::sync::atomic::{AtomicBool, Ordering};
use tokio_util::sync::CancellationToken;

#[derive(Clone, Debug, Default, Serialize, PartialEq)]
pub struct OllamaModelInfo {
    pub name: String,
    pub modified_at: String,
    pub size: i64,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct GenerateResponse {
    pub model: String,
    pub response: String,
    pub done: bool,
}

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
pub struct ChatStreamResponse {
    pub model: String,
    pub message: Message,
    pub done: bool,
}

#[derive(Clone, Debug, Default)]
pub struct GenerateOption {
    pub system: Option<String>,
    pub format: Option<Value>,
    pub temperature: Option<f32>,
    pub images: Vec<String>,
}

#[derive(Clone, Debug, Default)]
pub struct NativeChatOption {
    pub temperature: Option<f32>,
    pub format: Option<String>,
}

impl Client {
    /// Embeds inputs through Ollama's native API with cancellation.
    pub async fn embed_native_cancellable(
        &self,
        token: &CancellationToken,
        model: &str,
        inputs: &[String],
        dimensions: usize,
    ) -> Result<Vec<Vec<f32>>> {
        self.require_ollama("EmbedNative")?;
        let body = native_embedding_request(self, model, inputs, dimensions)?;
        cancel_on(token, async {
            let mut response = self
                .request_cancellable(reqwest::Method::POST, "/api/embed", Some(&body))
                .await?;
            let raw = read_reqwest_limited(&mut response, 64 << 20).await?;
            decode_native_embeddings(&raw, inputs.len())
        })
        .await
    }

    pub fn embed_native(
        &self,
        model: &str,
        inputs: &[String],
        dimensions: usize,
    ) -> Result<Vec<Vec<f32>>> {
        self.require_ollama("EmbedNative")?;
        let body = native_embedding_request(self, model, inputs, dimensions)?;
        let mut response = self.request("POST", "/api/embed", Some(&body))?;
        let raw = read_limited(&mut response, 64 << 20)?;
        decode_native_embeddings(&raw, inputs.len())
    }

    /// Lists Ollama models with cancellation while fetching the model list.
    pub async fn list_ollama_models_cancellable(
        &self,
        token: &CancellationToken,
    ) -> Result<Vec<OllamaModelInfo>> {
        self.require_ollama("ListOllamaModels")?;
        cancel_on(token, async {
            let mut response = self
                .request_cancellable(reqwest::Method::GET, "/api/tags", Option::<&()>::None)
                .await?;
            let raw = read_reqwest_limited(&mut response, 16 << 20).await?;
            decode_ollama_models(&raw)
        })
        .await
    }

    pub fn list_ollama_models(&self) -> Result<Vec<OllamaModelInfo>> {
        self.require_ollama("ListOllamaModels")?;
        let mut response = self.request("GET", "/api/tags", Option::<&()>::None)?;
        let raw = read_limited(&mut response, 16 << 20)?;
        decode_ollama_models(&raw)
    }

    /// Streams native model generation and cancels the request/read when asked.
    pub async fn generate_cancellable<F>(
        &self,
        token: &CancellationToken,
        model: &str,
        prompt: &str,
        options: &GenerateOption,
        mut callback: F,
    ) -> Result<()>
    where
        F: FnMut(GenerateResponse) -> Result<()>,
    {
        self.require_ollama("Generate")?;
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        let body = generate_request_body(model, prompt, options);
        self.stream_ndjson_cancellable(token, "/api/generate", &body, move |line| {
            let value: GenerateResponse = decode_go_json(line, "decode generate chunk")?;
            callback(value)
        })
        .await
    }

    pub fn generate<F>(
        &self,
        model: &str,
        prompt: &str,
        options: &GenerateOption,
        mut callback: F,
    ) -> Result<()>
    where
        F: FnMut(GenerateResponse) -> Result<()>,
    {
        self.require_ollama("Generate")?;
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        let body = generate_request_body(model, prompt, options);
        self.stream_ndjson("/api/generate", &body, |line| {
            let value: GenerateResponse = decode_go_json(line, "decode generate chunk")?;
            callback(value)
        })
    }

    pub fn chat_stream<F>(
        &self,
        model: &str,
        messages: &[Message],
        options: &NativeChatOption,
        mut callback: F,
    ) -> Result<()>
    where
        F: FnMut(ChatStreamResponse) -> Result<()>,
    {
        self.require_ollama("ChatStream")?;
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        let body = chat_stream_request_body(model, messages, options);
        self.stream_ndjson("/api/chat", &body, |line| {
            let value: ChatStreamResponse = decode_go_json(line, "decode chat chunk")?;
            callback(value)
        })
    }

    /// Streams native Ollama chat and cancels the request/read when asked.
    pub async fn chat_stream_cancellable<F>(
        &self,
        token: &CancellationToken,
        model: &str,
        messages: &[Message],
        options: &NativeChatOption,
        mut callback: F,
    ) -> Result<()>
    where
        F: FnMut(ChatStreamResponse) -> Result<()>,
    {
        self.require_ollama("ChatStream")?;
        let model = if model.is_empty() {
            self.descriptor().default_model()
        } else {
            model
        };
        let body = chat_stream_request_body(model, messages, options);
        self.stream_ndjson_cancellable(token, "/api/chat", &body, move |line| {
            let value: ChatStreamResponse = decode_go_json(line, "decode chat chunk")?;
            callback(value)
        })
        .await
    }

    pub fn ping(&self) -> Result<()> {
        self.require_ollama("Ping")?;
        self.list_models().map(|_| ())
    }

    /// Checks Ollama availability using the generic model discovery response
    /// parser, matching Go Ping's call through ListModels.
    pub async fn ping_cancellable(&self, token: &CancellationToken) -> Result<()> {
        self.require_ollama("Ping")?;
        self.list_models_cancellable(token).await.map(|_| ())
    }

    fn stream_ndjson<F>(&self, path: &str, body: &Value, mut callback: F) -> Result<()>
    where
        F: FnMut(&[u8]) -> Result<()>,
    {
        let mut response = self.request("POST", path, Some(body))?;
        let mut reader = BufReader::new(&mut response);
        let mut started = false;
        while let Some(line) = read_bounded_line(&mut reader, 4 * 1024 * 1024).map_err(|error| {
            Error::transport(if started {
                format!("stream interrupted: {error}")
            } else {
                error.to_string()
            })
        })? {
            let token = line.strip_suffix(b"\n").unwrap_or(&line);
            let token = token.strip_suffix(b"\r").unwrap_or(token);
            if token.is_empty() {
                continue;
            }
            started = true;
            callback(&line)?;
        }
        Ok(())
    }

    async fn stream_ndjson_cancellable<F>(
        &self,
        token: &CancellationToken,
        path: &str,
        body: &Value,
        mut callback: F,
    ) -> Result<()>
    where
        F: FnMut(&[u8]) -> Result<()>,
    {
        let started = AtomicBool::new(false);
        let operation = async {
            let mut response = self
                .request_cancellable(reqwest::Method::POST, path, Some(body))
                .await?;
            let mut pending = Vec::new();
            const MAX_LINE_BYTES: usize = 4 * 1024 * 1024;
            while let Some(chunk) = response.chunk().await.map_err(|error| {
                Error::transport(if started.load(Ordering::Acquire) {
                    format!("stream interrupted: {}", error.without_url())
                } else {
                    error.without_url().to_string()
                })
            })? {
                let mut offset = 0;
                while let Some(relative_newline) =
                    chunk[offset..].iter().position(|byte| *byte == b'\n')
                {
                    let end = offset + relative_newline + 1;
                    let segment = &chunk[offset..end];
                    if segment.len() > MAX_LINE_BYTES - pending.len() {
                        return Err(ndjson_line_error(started.load(Ordering::Acquire)));
                    }
                    pending.extend_from_slice(segment);
                    process_ndjson_line(&pending, &started, &mut callback)?;
                    pending.clear();
                    offset = end;
                }
                let remainder = &chunk[offset..];
                if remainder.len() > MAX_LINE_BYTES - pending.len() {
                    return Err(ndjson_line_error(started.load(Ordering::Acquire)));
                }
                pending.extend_from_slice(remainder);
            }
            if !pending.is_empty() {
                process_ndjson_line(&pending, &started, &mut callback)?;
            }
            Ok(())
        };
        tokio::select! {
            biased;
            _ = token.cancelled() => Err(ndjson_cancel_error(started.load(Ordering::Acquire))),
            result = operation => result,
        }
    }

    fn require_ollama(&self, method: &str) -> Result<()> {
        if self.descriptor().id == "ollama" {
            Ok(())
        } else {
            Err(Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: {method} is only available for the ollama provider"),
            ))
        }
    }
}

fn generate_request_body(model: &str, prompt: &str, options: &GenerateOption) -> Value {
    let mut body = json!({"model":model,"prompt":prompt,"stream":true});
    if let Some(value) = &options.system
        && !value.is_empty()
    {
        body["system"] = json!(value);
    }
    if let Some(value) = &options.format {
        body["format"] = value.clone();
    }
    if let Some(value) = options.temperature {
        body["temperature"] = json!(value);
    }
    if !options.images.is_empty() {
        body["images"] = json!(options.images);
    }
    body
}

fn chat_stream_request_body(
    model: &str,
    messages: &[Message],
    options: &NativeChatOption,
) -> Value {
    let mut body = json!({"model":model,"messages":messages,"stream":true});
    if let Some(value) = options.temperature {
        body["temperature"] = json!(value);
    }
    if let Some(value) = &options.format
        && !value.is_empty()
    {
        body["format"] = json!(value);
    }
    body
}

fn native_embedding_request(
    client: &Client,
    model: &str,
    inputs: &[String],
    dimensions: usize,
) -> Result<Value> {
    if inputs.is_empty() {
        return Err(Error::local(
            ErrorCode::ProviderError,
            "llmkit: embed inputs must not be empty",
        ));
    }
    let model = if model.is_empty() {
        client.descriptor().default_model()
    } else {
        model
    };
    if model.is_empty() {
        return Err(Error::local(
            ErrorCode::ProviderError,
            format!(
                "llmkit: model is required for provider {:?}",
                client.descriptor().id
            ),
        ));
    }
    let mut body = json!({"model":model,"input":inputs});
    if dimensions != 0 {
        body["dimensions"] = json!(dimensions);
    }
    Ok(body)
}

fn decode_native_embeddings(raw: &[u8], expected_count: usize) -> Result<Vec<Vec<f32>>> {
    let parsed: NativeEmbeddingResponse = serde_json::from_slice(raw).map_err(|e| {
        Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: decode native embeddings response: {e}"),
        )
    })?;
    if parsed.embeddings.len() != expected_count {
        return Err(Error::local(
            ErrorCode::ProviderError,
            format!(
                "llmkit: expected {expected_count} embeddings, got {}",
                parsed.embeddings.len()
            ),
        ));
    }
    Ok(parsed.embeddings)
}

fn decode_ollama_models(raw: &[u8]) -> Result<Vec<OllamaModelInfo>> {
    let parsed: OllamaModelsResponse = serde_json::from_slice(raw).map_err(|e| {
        Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: decode Ollama model list: {e}"),
        )
    })?;
    Ok(parsed.models)
}

fn process_ndjson_line<F>(line: &[u8], started: &AtomicBool, callback: &mut F) -> Result<()>
where
    F: FnMut(&[u8]) -> Result<()>,
{
    let token = line.strip_suffix(b"\n").unwrap_or(line);
    let token = token.strip_suffix(b"\r").unwrap_or(token);
    if token.is_empty() {
        return Ok(());
    }
    started.store(true, Ordering::Release);
    callback(line)
}

fn ndjson_line_error(started: bool) -> Error {
    Error::transport(if started {
        "stream interrupted: bufio.Scanner: token too long".to_owned()
    } else {
        "bufio.Scanner: token too long".to_owned()
    })
}

fn ndjson_cancel_error(started: bool) -> Error {
    Error::transport(if started {
        "stream interrupted: context canceled".to_owned()
    } else {
        "context canceled".to_owned()
    })
}

fn decode_go_json<T: DeserializeOwned>(line: &[u8], operation: &str) -> Result<T> {
    match serde_json::from_slice(line) {
        Ok(value) => Ok(value),
        Err(decode_error) => {
            let detail = match serde_json::from_slice::<Value>(line) {
                Err(syntax_error) => go_json_error(line, &syntax_error),
                Ok(_) => decode_error.to_string(),
            };
            Err(Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: {operation}: {detail}"),
            ))
        }
    }
}

pub(crate) fn go_json_error(line: &[u8], error: &serde_json::Error) -> String {
    let line = line.strip_suffix(b"\n").unwrap_or(line);
    let line = line.strip_suffix(b"\r").unwrap_or(line);
    let message = error.to_string();

    if error.is_eof() {
        return "unexpected end of JSON input".to_owned();
    }
    if message.contains("key must be a string")
        && let Some(byte) = line.iter().enumerate().find_map(|(index, byte)| {
            if *byte != b'{' && *byte != b',' {
                return None;
            }
            line[index + 1..]
                .iter()
                .copied()
                .find(|next| !next.is_ascii_whitespace())
                .filter(|next| *next != b'"')
        })
    {
        return format!(
            "invalid character '{}' looking for beginning of object key string",
            char::from(byte)
        );
    }
    if message.contains("trailing characters")
        && let Some(byte) = serde_error_position_byte(line, error)
    {
        return format!(
            "invalid character '{}' after top-level value",
            char::from(byte)
        );
    }
    message
}

fn serde_error_position_byte(line: &[u8], error: &serde_json::Error) -> Option<u8> {
    let source_line = line
        .split(|byte| *byte == b'\n')
        .nth(error.line().checked_sub(1)?)?;
    source_line.get(error.column().checked_sub(1)?).copied()
}

#[derive(Deserialize)]
struct NativeEmbeddingResponse {
    embeddings: Vec<Vec<f32>>,
}
struct OllamaModelsResponse {
    models: Vec<OllamaModelInfo>,
}

impl<'de> Deserialize<'de> for OllamaModelsResponse {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct OllamaModelsVisitor;

        impl<'de> Visitor<'de> for OllamaModelsVisitor {
            type Value = OllamaModelsResponse;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an Ollama model-list response object")
            }

            fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                Ok(OllamaModelsResponse { models: Vec::new() })
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut models = Vec::new();
                while let Some(key) = map.next_key::<String>()? {
                    if key.eq_ignore_ascii_case("models") {
                        models = map
                            .next_value::<Option<Vec<OllamaModelInfo>>>()?
                            .unwrap_or_default();
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(OllamaModelsResponse { models })
            }
        }

        deserializer.deserialize_any(OllamaModelsVisitor)
    }
}

impl<'de> Deserialize<'de> for OllamaModelInfo {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct OllamaModelInfoVisitor;

        impl<'de> Visitor<'de> for OllamaModelInfoVisitor {
            type Value = OllamaModelInfo;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an Ollama model metadata object")
            }

            fn visit_unit<E>(self) -> std::result::Result<Self::Value, E>
            where
                E: serde::de::Error,
            {
                Ok(OllamaModelInfo::default())
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut model = OllamaModelInfo::default();
                while let Some(key) = map.next_key::<String>()? {
                    if key.eq_ignore_ascii_case("name") {
                        if let Some(value) = map.next_value::<Option<String>>()? {
                            model.name = value;
                        }
                    } else if key.eq_ignore_ascii_case("modified_at") {
                        if let Some(value) = map.next_value::<Option<String>>()? {
                            model.modified_at = value;
                        }
                    } else if key.eq_ignore_ascii_case("size") {
                        if let Some(value) = map.next_value::<Option<i64>>()? {
                            model.size = value;
                        }
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(model)
            }
        }

        deserializer.deserialize_any(OllamaModelInfoVisitor)
    }
}
