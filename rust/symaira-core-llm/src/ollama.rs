use crate::chat::{Message, read_bounded_line};
use crate::client::{Client, read_limited};
use crate::error::{Error, ErrorCode, Result};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::io::BufReader;

#[derive(Clone, Debug, Default, Deserialize, Serialize, PartialEq)]
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
            let value: GenerateResponse = serde_json::from_slice(line).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: decode generate chunk: {e}"),
                )
            })?;
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
            let value: ChatStreamResponse = serde_json::from_slice(line).map_err(|e| {
                Error::local(
                    ErrorCode::ProviderError,
                    format!("llmkit: decode chat chunk: {e}"),
                )
            })?;
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
        while let Some(line) = read_bounded_line(&mut reader, 1024 * 1024).map_err(|error| {
            Error::transport(if started {
                format!("stream interrupted: {error}")
            } else {
                error.to_string()
            })
        })? {
            if line.iter().all(u8::is_ascii_whitespace) {
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

#[derive(Deserialize)]
struct NativeEmbeddingResponse {
    embeddings: Vec<Vec<f32>>,
}
#[derive(Deserialize)]
struct OllamaModelsResponse {
    #[serde(default)]
    models: Vec<OllamaModelInfo>,
}
