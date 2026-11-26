//! Test helper that gates the size of a server's `tools/list` catalog.

use serde::{Deserialize, Serialize, de::IgnoredAny};

/// The exact tool count and UTF-8 byte length of a serialized `tools/list` result.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct McpCatalogSize {
    pub tool_count: usize,
    pub bytes: usize,
}

impl McpCatalogSize {
    /// Measures the serialized result, excluding the JSON-RPC envelope.
    /// Serialize this record as JSON to regenerate a baseline.
    pub fn measure(catalog_json: &[u8]) -> serde_json::Result<Self> {
        #[derive(Deserialize)]
        struct Catalog {
            tools: Vec<IgnoredAny>,
        }

        let catalog: Catalog = serde_json::from_slice(catalog_json)?;
        Ok(Self {
            tool_count: catalog.tools.len(),
            bytes: catalog_json.len(),
        })
    }
}

/// Checks the compact catalog bytes (for example, from `Server::catalog_json`)
/// against a committed `mcp-catalog.json` record passed with `include_bytes!`.
///
/// # Panics
///
/// Panics on invalid JSON, a different tool count, or a byte-size change greater
/// than 10% in either direction from the recorded size. The failure includes the
/// caller's regeneration command (for example, `make update-mcp-catalog`).
#[track_caller]
pub fn assert_mcp_catalog_size(catalog_json: &[u8], record_json: &[u8], regenerate: &str) {
    let expected: McpCatalogSize = serde_json::from_slice(record_json).unwrap_or_else(|err| {
        panic!("Invalid MCP catalog size record: {err}. Regenerate with: {regenerate}")
    });
    let actual = McpCatalogSize::measure(catalog_json).unwrap_or_else(|err| {
        panic!("Invalid MCP tools/list result: {err}. Regenerate with: {regenerate}")
    });

    assert!(
        actual.tool_count == expected.tool_count
            && actual.bytes.abs_diff(expected.bytes) <= expected.bytes / 10,
        "MCP catalog drift: expected {} tools and {} bytes (up to 10% byte drift), got {} tools and {} bytes. Regenerate with: {regenerate}",
        expected.tool_count,
        expected.bytes,
        actual.tool_count,
        actual.bytes,
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    const CATALOG: &str = r#"{"tools":[{"name":"one","description":"é"},{"name":"two"}]}"#;
    const RECORD: &[u8] = include_bytes!("../fixtures/mcp-catalog.json");
    const REGENERATE: &str = "make update-mcp-catalog";

    #[test]
    fn matches_committed_record_and_accepts_exactly_ten_percent_drift() {
        let actual = McpCatalogSize::measure(CATALOG.as_bytes()).unwrap();
        let expected: McpCatalogSize = serde_json::from_slice(RECORD).unwrap();
        assert_eq!(actual, expected);
        assert_eq!(actual.bytes, CATALOG.chars().count() + 1);
        assert_mcp_catalog_size(CATALOG.as_bytes(), RECORD, REGENERATE);
        let larger = CATALOG.replace('é', "é123456");
        assert_mcp_catalog_size(larger.as_bytes(), RECORD, REGENERATE);
    }

    #[test]
    #[should_panic(expected = "got 2 tools and 60 bytes. Regenerate with: make update-mcp-catalog")]
    fn wrong_tool_count_fails_even_with_exact_byte_size() {
        assert_mcp_catalog_size(
            CATALOG.as_bytes(),
            br#"{"tool_count":1,"bytes":60}"#,
            REGENERATE,
        );
    }

    #[test]
    #[should_panic(expected = "got 2 tools and 67 bytes. Regenerate with: make update-mcp-catalog")]
    fn wrong_byte_size_fails_even_with_exact_tool_count() {
        let larger = CATALOG.replace('é', "é1234567");
        assert_mcp_catalog_size(larger.as_bytes(), RECORD, REGENERATE);
    }
}
