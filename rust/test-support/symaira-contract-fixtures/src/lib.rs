#![deny(unsafe_code)]

//! Embedded language-neutral CoreKit contract fixtures.

pub const EXIT_CODES: &[u8] = include_bytes!("../fixtures/contracts/exit_codes.json");
pub const CONFIG_PATHS: &[u8] = include_bytes!("../fixtures/contracts/config_paths.json");
pub const JSON_ENCODING: &[u8] = include_bytes!("../fixtures/contracts/json_encoding.json");
pub const MCP_TOOL_ANNOTATIONS: &[u8] =
    include_bytes!("../fixtures/contracts/mcp_tool_annotations.json");
pub const MCP_TOOL_ERRORS: &[u8] = include_bytes!("../fixtures/contracts/mcp_tool_errors.json");
pub const SECRET_REFS: &[u8] = include_bytes!("../fixtures/contracts/secret_refs.json");
pub const UPDATE_CHECK_INVARIANTS: &[u8] =
    include_bytes!("../fixtures/contracts/update_check_invariants.json");
pub const LLM_PROVIDERS: &[u8] = include_bytes!("../fixtures/contracts/llm_providers.json");
pub const LLM_ERRORS: &[u8] = include_bytes!("../fixtures/contracts/llm_errors.json");

pub const FOUNDATION_VER_001: &[u8] = include_bytes!("../fixtures/foundation/ver-001.json");
pub const FOUNDATION_VER_002: &[u8] = include_bytes!("../fixtures/foundation/ver-002.json");
pub const FOUNDATION_EXIT_001: &[u8] = include_bytes!("../fixtures/foundation/exit-001.json");
pub const FOUNDATION_EXIT_002: &[u8] = include_bytes!("../fixtures/foundation/exit-002.json");
pub const FOUNDATION_EXIT_003: &[u8] = include_bytes!("../fixtures/foundation/exit-003.json");
pub const FOUNDATION_EXIT_004: &[u8] = include_bytes!("../fixtures/foundation/exit-004.json");
pub const FOUNDATION_ENV_001: &[u8] = include_bytes!("../fixtures/foundation/env-001.json");
pub const FOUNDATION_ENV_002: &[u8] = include_bytes!("../fixtures/foundation/env-002.json");
pub const FOUNDATION_LOG_001: &[u8] = include_bytes!("../fixtures/foundation/log-001.json");
pub const FOUNDATION_LOG_002: &[u8] = include_bytes!("../fixtures/foundation/log-002.json");
pub const FOUNDATION_LOG_003: &[u8] = include_bytes!("../fixtures/foundation/log-003.json");
pub const FOUNDATION_LOG_004: &[u8] = include_bytes!("../fixtures/foundation/log-004.json");
pub const FOUNDATION_CFG_001: &[u8] = include_bytes!("../fixtures/foundation/cfg-001.json");
pub const FOUNDATION_CFG_002: &[u8] = include_bytes!("../fixtures/foundation/cfg-002.json");
pub const FOUNDATION_CFG_003: &[u8] = include_bytes!("../fixtures/foundation/cfg-003.json");
pub const FOUNDATION_CFG_004: &[u8] = include_bytes!("../fixtures/foundation/cfg-004.json");
pub const FOUNDATION_CFG_005: &[u8] = include_bytes!("../fixtures/foundation/cfg-005.json");
pub const FOUNDATION_CFG_006: &[u8] = include_bytes!("../fixtures/foundation/cfg-006.json");
pub const FOUNDATION_CFG_007: &[u8] = include_bytes!("../fixtures/foundation/cfg-007.json");

pub const FOUNDATION_FIXTURE_IDS: &[&str] = &[
    "VER-001", "VER-002", "EXIT-001", "EXIT-002", "EXIT-003", "EXIT-004", "ENV-001", "ENV-002",
    "LOG-001", "LOG-002", "LOG-003", "LOG-004", "CFG-001", "CFG-002", "CFG-003", "CFG-004",
    "CFG-005", "CFG-006", "CFG-007",
];

pub fn foundation(id: &str) -> &'static [u8] {
    match id {
        "VER-001" => FOUNDATION_VER_001,
        "VER-002" => FOUNDATION_VER_002,
        "EXIT-001" => FOUNDATION_EXIT_001,
        "EXIT-002" => FOUNDATION_EXIT_002,
        "EXIT-003" => FOUNDATION_EXIT_003,
        "EXIT-004" => FOUNDATION_EXIT_004,
        "ENV-001" => FOUNDATION_ENV_001,
        "ENV-002" => FOUNDATION_ENV_002,
        "LOG-001" => FOUNDATION_LOG_001,
        "LOG-002" => FOUNDATION_LOG_002,
        "LOG-003" => FOUNDATION_LOG_003,
        "LOG-004" => FOUNDATION_LOG_004,
        "CFG-001" => FOUNDATION_CFG_001,
        "CFG-002" => FOUNDATION_CFG_002,
        "CFG-003" => FOUNDATION_CFG_003,
        "CFG-004" => FOUNDATION_CFG_004,
        "CFG-005" => FOUNDATION_CFG_005,
        "CFG-006" => FOUNDATION_CFG_006,
        "CFG-007" => FOUNDATION_CFG_007,
        _ => panic!("unknown foundation fixture {id}"),
    }
}

pub fn json(bytes: &'static [u8]) -> serde_json::Value {
    serde_json::from_slice(bytes).expect("embedded contract fixture must be valid JSON")
}
