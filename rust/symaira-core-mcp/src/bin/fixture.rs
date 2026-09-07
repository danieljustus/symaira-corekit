use schemars::JsonSchema;
use serde::Deserialize;
use serde::de::{self, Deserializer};
use serde_json::{Map, Value};
use std::fmt;
use std::io;
use symaira_core_mcp::{Server, Tool, ToolAnnotations, ToolError, ToolOutput, ToolResult};

#[derive(Debug)]
struct WrappedToolError(ToolError);

impl fmt::Display for WrappedToolError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(formatter, "wrapped: {}", self.0)
    }
}

impl std::error::Error for WrappedToolError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.0)
    }
}

#[derive(Debug, Default, JsonSchema)]
struct TypedInput {
    query: String,
}

impl<'de> Deserialize<'de> for TypedInput {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let value = Value::deserialize(deserializer)?;
        let Value::Object(fields) = value else {
            return Err(de::Error::custom(format!(
                "json: cannot unmarshal {} into Go value of type main.typedInput",
                go_json_kind(&value)
            )));
        };
        let Some(query) = fields.get("query") else {
            return Ok(Self::default());
        };
        let query = match query {
            Value::String(value) => value.clone(),
            Value::Null => String::new(),
            value => {
                return Err(de::Error::custom(format!(
                    "json: cannot unmarshal {} into Go struct field typedInput.query of type string",
                    go_json_kind(value)
                )));
            }
        };
        Ok(Self { query })
    }
}

fn go_json_kind(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "bool",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn decode_fixture(value: Value) -> Result<String, String> {
    if value.is_null() {
        return Ok(String::new());
    }
    let Value::Object(fields) = value else {
        return Err(format!(
            "json: cannot unmarshal {} into Go value of type main.fixture",
            go_json_kind(&value)
        ));
    };
    let Some(message) = fields.get("message") else {
        return Ok(String::new());
    };
    match message {
        Value::String(value) => Ok(value.clone()),
        Value::Null => Ok(String::new()),
        value => Err(format!(
            "json: cannot unmarshal {} into Go struct field fixture.message of type string",
            go_json_kind(value)
        )),
    }
}

fn main() {
    let server = Server::new("fixture", "1.0.0");
    server
        .register_tool(
            Tool::new("echo", "Echo input")
                .schema(
                    serde_json::json!({"type":"object","properties":{"message":{"type":"string"}}}),
                )
                .handler(|_, arguments| {
                    decode_fixture(arguments)
                        .map(ToolOutput::from)
                        .map_err(|error| {
                            Box::new(ToolError::new(error))
                                as Box<dyn std::error::Error + Send + Sync>
                        })
                }),
        )
        .expect("fixture tool registration");
    server
        .register_typed::<TypedInput, _>("typed", "Typed input", |_, input| {
            Ok(ToolOutput::from(input.query))
        })
        .expect("fixture typed tool registration");
    server
        .register_tool(
            Tool::new("number", "Return structured JSON")
                .handler(|_, _| Ok(ToolOutput::from(serde_json::json!({"free":[39000,39001]})))),
        )
        .expect("fixture tool registration");
    server
        .register_tool(Tool::new("rich", "Return rich content").handler(|_, _| {
            let mut text = Map::new();
            text.insert("type".to_string(), Value::String("text".to_string()));
            text.insert("text".to_string(), Value::String("hello".to_string()));
            let mut image = Map::new();
            image.insert("type".to_string(), Value::String("image".to_string()));
            image.insert("data".to_string(), Value::String("aGVsbG8=".to_string()));
            image.insert(
                "mimeType".to_string(),
                Value::String("image/png".to_string()),
            );
            Ok(ToolOutput::Result(ToolResult {
                content: vec![text, image],
                structured_content: Some(serde_json::json!({"count":2})),
                meta: None,
            }))
        }))
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("fail", "Return a structured error").handler(|_, _| {
                Err(Box::new(
                    ToolError::new("denied")
                        .code("denied")
                        .retryable(false)
                        .hint("check policy"),
                ))
            }),
        )
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("panic", "Panic for recovery").handler(|_, _| panic!("fixture panic")),
        )
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("read", "Read-only annotated tool").annotations(ToolAnnotations {
                title: "Read".to_string(),
                read_only_hint: true,
                idempotent_hint: true,
                ..ToolAnnotations::default()
            }),
        )
        .expect("fixture tool registration");
    server
        .register_tool(Tool::new("all-hints", "All annotation hints").annotations(
            ToolAnnotations {
                title: "All".to_string(),
                read_only_hint: true,
                idempotent_hint: true,
                open_world_hint: true,
                destructive_hint: true,
            },
        ))
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("false-hints", "Explicit false annotation hints")
                .annotations(ToolAnnotations::default()),
        )
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("bool", "Return boolean")
                .handler(|_, _| Ok(ToolOutput::from(Value::Bool(true)))),
        )
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("special", "Return HTML-sensitive JSON").handler(|_, _| {
                Ok(ToolOutput::from(serde_json::json!({
                    "text": "<>&\u{2028}\u{2029}"
                })))
            }),
        )
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new(
                "special-structured",
                "Return HTML-sensitive structured JSON",
            )
            .handler(|_, _| {
                Ok(ToolOutput::Result(ToolResult {
                    content: vec![],
                    structured_content: Some(serde_json::json!({
                        "text": "<>&\u{2028}\u{2029}"
                    })),
                    meta: None,
                }))
            }),
        )
        .expect("fixture tool registration");
    server
        .register_tool(Tool::new("plain", "Return a plain error").handler(|_, _| {
            Err(Box::new(io::Error::other("plain failure"))
                as Box<dyn std::error::Error + Send + Sync>)
        }))
        .expect("fixture tool registration");
    server
        .register_tool(
            Tool::new("wrapped", "Return a wrapped structured error").handler(|_, _| {
                Err(Box::new(WrappedToolError(
                    ToolError::new("denied")
                        .code("denied")
                        .retryable(false)
                        .hint("check policy"),
                ))
                    as Box<dyn std::error::Error + Send + Sync>)
            }),
        )
        .expect("fixture tool registration");

    if let Err(error) = server.serve_stdio() {
        eprintln!("mcp fixture: {error}");
        std::process::exit(1);
    }
}
