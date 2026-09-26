#![deny(unsafe_code)]

//! Shared, descriptor-driven LLM HTTP transports.

mod chat;
mod client;
mod embeddings;
mod error;
mod ollama;
mod provider;

pub use chat::{ChatOptions, Choice, Message, Tool, ToolCall};
pub use client::{Client, ClientBuilder, DEFAULT_TIMEOUT};
pub use embeddings::Embedding;
pub use error::{Error, ErrorCode, Result};
pub use ollama::{
    ChatStreamResponse, GenerateOption, GenerateResponse, NativeChatOption, OllamaModelInfo,
};
pub use provider::{
    AuthScheme, Capabilities, Descriptor, ModelInfo, ModelSource, WireDialect, lookup, providers,
};
pub use ureq::Agent;
