use serde::{Deserialize, Serialize};
use std::sync::OnceLock;

const REGISTRY_JSON: &str = include_str!("../../../llmkit/providers.json");

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum AuthScheme {
    Bearer,
    Header,
    None,
}

#[derive(Clone, Copy, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum WireDialect {
    Openai,
    Anthropic,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Capabilities {
    pub streaming: bool,
    pub tool_use: bool,
    pub embeddings: bool,
    pub vision: bool,
    pub system_prompt: bool,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ModelSource {
    pub mode: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub discovery_path: String,
    pub default: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Descriptor {
    pub id: String,
    pub display_name: String,
    #[serde(default, deserialize_with = "null_string")]
    pub base_url: String,
    pub base_url_overridable: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub base_url_required_override: bool,
    pub auth_scheme: AuthScheme,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub auth_header: String,
    #[serde(default, skip_serializing_if = "std::collections::BTreeMap::is_empty")]
    pub extra_headers: std::collections::BTreeMap<String, String>,
    pub dialect: WireDialect,
    #[serde(default, skip_serializing_if = "is_false")]
    pub dialect_configurable: bool,
    pub capabilities: Capabilities,
    pub models: ModelSource,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub credential_env_default: String,
}

fn is_false(value: &bool) -> bool {
    !value
}

#[derive(Deserialize)]
struct Registry {
    schema_version: u32,
    providers: Vec<Descriptor>,
}

fn null_string<'de, D: serde::Deserializer<'de>>(deserializer: D) -> Result<String, D::Error> {
    Ok(Option::<String>::deserialize(deserializer)?.unwrap_or_default())
}

fn registry() -> &'static Registry {
    static REGISTRY: OnceLock<Registry> = OnceLock::new();
    REGISTRY.get_or_init(|| {
        serde_json::from_str(REGISTRY_JSON).expect("checked-in LLM registry is valid")
    })
}

impl Descriptor {
    pub fn default_model(&self) -> &str {
        self.models.default.as_deref().unwrap_or_default()
    }

    pub fn validate(&self) -> Result<(), String> {
        if self.base_url.is_empty() && !self.base_url_required_override {
            return Err(format!(
                "llmkit: provider {:?} has no base URL and none was provided",
                self.id
            ));
        }
        Ok(())
    }
}

pub fn providers() -> &'static [Descriptor] {
    debug_assert_eq!(registry().schema_version, 1);
    &registry().providers
}

pub fn lookup(id: &str) -> Option<&'static Descriptor> {
    providers()
        .iter()
        .find(|provider| provider.id.eq_ignore_ascii_case(id))
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct ModelInfo {
    pub id: String,
}
