use crate::client::{Client, read_limited};
use crate::error::{Error, ErrorCode, Result};
use crate::provider::ModelInfo;
use serde::de::{Error as _, IgnoredAny, MapAccess, Visitor};
use serde::{Deserialize, Deserializer};
use serde_json::json;
use std::fmt;

#[derive(Clone, Debug, Deserialize, PartialEq)]
pub struct Embedding {
    pub vector: Vec<f32>,
    pub model: String,
}

impl Client {
    pub fn embed(
        &self,
        model: &str,
        inputs: &[String],
        dimensions: Option<usize>,
    ) -> Result<Vec<Embedding>> {
        if !self.descriptor().capabilities.embeddings {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} does not promise embeddings",
                    self.descriptor().id
                ),
            ));
        }
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
        if let Some(n) = dimensions.filter(|n| *n > 0) {
            body["dimensions"] = json!(n);
        }
        let mut response = self.request("POST", "/embeddings", Some(&body))?;
        let raw = read_limited(&mut response, 64 << 20)?;
        let parsed: EmbeddingResponse = serde_json::from_slice(&raw).map_err(|e| {
            Error::local(
                ErrorCode::ProviderError,
                format!("llmkit: decode embeddings response: {e}"),
            )
        })?;
        if parsed.data.len() != inputs.len() {
            return Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: expected {} embeddings, got {}",
                    inputs.len(),
                    parsed.data.len()
                ),
            ));
        }
        Ok(parsed
            .data
            .into_iter()
            .map(|item| Embedding {
                vector: item.embedding,
                model: model.to_owned(),
            })
            .collect())
    }

    pub fn list_models(&self) -> Result<Vec<ModelInfo>> {
        match self.descriptor().models.mode.as_str() {
            "static" => Ok(if self.descriptor().default_model().is_empty() {
                Vec::new()
            } else {
                vec![ModelInfo {
                    id: self.descriptor().default_model().to_owned(),
                }]
            }),
            "discovered" => {
                let path = &self.descriptor().models.discovery_path;
                if path.is_empty() {
                    return Err(Error::local(
                        ErrorCode::ProviderError,
                        format!(
                            "llmkit: provider {:?} declares discovery without discovery_path",
                            self.descriptor().id
                        ),
                    ));
                }
                self.discover_models(path)
            }
            mode => Err(Error::local(
                ErrorCode::ProviderError,
                format!(
                    "llmkit: provider {:?} models.mode {:?} has no client-side listing",
                    self.descriptor().id,
                    mode
                ),
            )),
        }
    }

    fn discover_models(&self, path: &str) -> Result<Vec<ModelInfo>> {
        let mut response = self.request("GET", path, Option::<&()>::None)?;
        let raw = read_limited(&mut response, 16 << 20)?;
        if let Ok(parsed) = serde_json::from_slice::<OpenAiModelList>(&raw)
            && !parsed.data.is_empty()
        {
            return Ok(parsed
                .data
                .into_iter()
                .map(|model| ModelInfo { id: model.id })
                .collect());
        }
        if let Ok(parsed) = serde_json::from_slice::<OllamaModelList>(&raw)
            && let Some(models) = parsed.models
        {
            return Ok(models
                .into_iter()
                .map(|model| ModelInfo { id: model.name })
                .collect());
        }
        Err(Error::local(
            ErrorCode::ProviderError,
            format!("llmkit: unrecognized discovery response shape at {path}"),
        ))
    }
}

struct EmbeddingResponse {
    data: Vec<EmbeddingData>,
}
struct EmbeddingData {
    embedding: Vec<f32>,
}

impl<'de> Deserialize<'de> for EmbeddingResponse {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct EmbeddingResponseVisitor;

        impl<'de> Visitor<'de> for EmbeddingResponseVisitor {
            type Value = EmbeddingResponse;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an embedding response object")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut data = None;
                while let Some(key) = map.next_key::<String>()? {
                    if key.eq_ignore_ascii_case("data") {
                        data = Some(map.next_value()?);
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(EmbeddingResponse {
                    data: data.ok_or_else(|| M::Error::missing_field("data"))?,
                })
            }
        }

        deserializer.deserialize_map(EmbeddingResponseVisitor)
    }
}

impl<'de> Deserialize<'de> for EmbeddingData {
    fn deserialize<D>(deserializer: D) -> std::result::Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct EmbeddingDataVisitor;

        impl<'de> Visitor<'de> for EmbeddingDataVisitor {
            type Value = EmbeddingData;

            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("an embedding data object")
            }

            fn visit_map<M>(self, mut map: M) -> std::result::Result<Self::Value, M::Error>
            where
                M: MapAccess<'de>,
            {
                let mut embedding = None;
                while let Some(key) = map.next_key::<String>()? {
                    if key.eq_ignore_ascii_case("embedding") {
                        embedding = Some(map.next_value()?);
                    } else {
                        let _: IgnoredAny = map.next_value()?;
                    }
                }
                Ok(EmbeddingData {
                    embedding: embedding.ok_or_else(|| M::Error::missing_field("embedding"))?,
                })
            }
        }

        deserializer.deserialize_map(EmbeddingDataVisitor)
    }
}

#[derive(Deserialize)]
struct OpenAiModelList {
    data: Vec<ModelId>,
}
#[derive(Deserialize)]
struct ModelId {
    id: String,
}
#[derive(Deserialize)]
struct OllamaModelList {
    models: Option<Vec<OllamaModel>>,
}
#[derive(Deserialize)]
struct OllamaModel {
    name: String,
}
