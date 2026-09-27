use crate::chat::{Message, read_bounded_line};
use crate::client::{Client, read_limited};
use crate::error::{Error, ErrorCode, Result};
use serde::Deserializer;
use serde::de::{DeserializeOwned, IgnoredAny, MapAccess, Visitor};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::fmt;
use std::io::BufReader;

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
    pub fn embed_native(
        &self,
        model: &str,
        inputs: &[String],
        dimensions: usize,
    ) -> Result<Vec<Vec<f32>>> {
        self.require_ollama("EmbedNative")?;
        if inputs.is_empty() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                "llmkit: embed inputs must not be empty",
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
        let mut body = json!({"model":model,"input":inputs});
        if dimensions != 0 {
            body["dimensions"] = json!(dimensions);
        }
        let mut response = self.request("POST", "/api/embed", Some(&body))?;
        let raw = read_limited(&mut response, 64 << 20)?;
        let parsed: NativeEmbeddingResponse = serde_json::from_slice(&raw).map_err(|e| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode native embeddings response: {e}"),
            )
        })?;
        if parsed.embeddings.len() != inputs.len() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: expected {} embeddings, got {}",
                    inputs.len(),
                    parsed.embeddings.len()
                ),
            ));
        }
        Ok(parsed.embeddings)
    }

    pub fn list_ollama_models(&self) -> Result<Vec<OllamaModelInfo>> {
        self.require_ollama("ListOllamaModels")?;
        let mut response = self.request("GET", "/api/tags", Option::<&()>::None)?;
        let raw = read_limited(&mut response, 16 << 20)?;
        let parsed: OllamaModelsResponse = serde_json::from_slice(&raw).map_err(|e| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode Ollama model list: {e}"),
            )
        })?;
        Ok(parsed.models)
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
        let mut body = json!({"model":model,"messages":messages,"stream":true});
        if let Some(value) = options.temperature {
            body["temperature"] = json!(value);
        }
        if let Some(value) = &options.format
            && !value.is_empty()
        {
            body["format"] = json!(value);
        }
        self.stream_ndjson("/api/chat", &body, |line| {
            let value: ChatStreamResponse = decode_go_json(line, "decode chat chunk")?;
            callback(value)
        })
    }

    pub fn ping(&self) -> Result<()> {
        self.require_ollama("Ping")?;
        self.list_ollama_models().map(|_| ())
    }

    fn stream_ndjson<F>(&self, path: &str, body: &Value, mut callback: F) -> Result<()>
    where
        F: FnMut(&[u8]) -> Result<()>,
    {
        let mut response = self.request("POST", path, Some(body))?;
        let mut reader = BufReader::new(response.body_mut().as_reader());
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

fn go_json_error(line: &[u8], error: &serde_json::Error) -> String {
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
