#![deny(unsafe_code)]

//! Version handshake payload shared by Symaira command-line tools.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::io::{self, Write};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Info {
    pub tool: String,
    pub version: String,
    pub schema_version: i32,
}

pub fn new(tool: impl Into<String>, version: impl Into<String>, schema_version: i32) -> Info {
    Info {
        tool: tool.into(),
        version: version.into(),
        schema_version,
    }
}

#[derive(Debug)]
pub enum WriteError {
    Encode(serde_json::Error),
    Io(io::Error),
}

impl fmt::Display for WriteError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Encode(error) => write!(f, "encode version payload: {error}"),
            Self::Io(error) => write!(f, "write version payload: {error}"),
        }
    }
}

impl std::error::Error for WriteError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Encode(error) => Some(error),
            Self::Io(error) => Some(error),
        }
    }
}

impl From<serde_json::Error> for WriteError {
    fn from(error: serde_json::Error) -> Self {
        Self::Encode(error)
    }
}

impl From<io::Error> for WriteError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

impl Info {
    /// Encode compact JSON in declaration order, matching Go's json.Marshal.
    pub fn json(&self) -> Result<Vec<u8>, serde_json::Error> {
        let encoded = serde_json::to_string(self)?;
        Ok(encoded
            .replace('&', "\\u0026")
            .replace('<', "\\u003c")
            .replace('>', "\\u003e")
            .replace('\u{2028}', "\\u2028")
            .replace('\u{2029}', "\\u2029")
            .into_bytes())
    }

    /// Write compact JSON followed by exactly one newline.
    pub fn write<W: Write>(&self, mut writer: W) -> Result<(), WriteError> {
        writer.write_all(&self.json()?)?;
        writer.write_all(b"\n")?;
        Ok(())
    }
}

impl fmt::Display for Info {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{} {}", self.tool, self.version)
    }
}
