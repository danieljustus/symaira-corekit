//! Contract tests for the MCFG rows: the behaviours the Go oracle pins.
//!
//! These run standalone; `scripts/rust-port/mcpcfg-differential.py` proves the
//! same behaviours byte-for-byte against the pinned Go implementation.

use std::collections::BTreeMap;

use symaira_core_mcpcfg::{
    Client, ConfigError, DEFAULT_SERVERS_KEY, Fs, ScanSource, Status, discover, jsonc_strip,
    normalize_key, parse_config_file, scan_all_with_fs, scan_source_with_fs,
};

/// In-memory filesystem mirroring the harness fixture.
struct MemFs {
    files: BTreeMap<String, String>,
    glob: BTreeMap<String, Vec<String>>,
    glob_error: Vec<String>,
}

impl MemFs {
    fn new() -> Self {
        Self {
            files: BTreeMap::new(),
            glob: BTreeMap::new(),
            glob_error: Vec::new(),
        }
    }

    fn with_file(mut self, path: &str, contents: &str) -> Self {
        self.files.insert(path.to_owned(), contents.to_owned());
        self
    }
}

impl Fs for MemFs {
    fn read_file(&self, path: &str) -> std::io::Result<Vec<u8>> {
        match self.files.get(path) {
            Some(contents) => Ok(contents.as_bytes().to_vec()),
            None => Err(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "no such file",
            )),
        }
    }

    fn glob(&self, pattern: &str) -> std::io::Result<Vec<String>> {
        if self.glob_error.iter().any(|item| item == pattern) {
            return Err(std::io::Error::other("glob failed"));
        }
        Ok(self.glob.get(pattern).cloned().unwrap_or_default())
    }
}

fn hermes() -> ScanSource {
    ScanSource::new(
        Client::Hermes,
        "/cfg/hermes/config.json",
        DEFAULT_SERVERS_KEY,
    )
}

fn opencode() -> ScanSource {
    ScanSource::new(Client::OpenCode, "/cfg/opencode/config.json", "mcp")
}

/// MCFG-001 — comments are stripped only outside strings, and entries survive.
#[test]
fn mcfg_001_jsonc_keeps_urls_and_string_escapes() {
    let contents = "{\n // line\n /* block */\n \"mcpServers\": {\n  \
        \"alpha\": {\"command\": \"npx\", \"args\": [\"-y\", \"pkg\"]},\n  \
        \"beta\": {\"url\": \"https://example.test/mcp/*x*//y\", \"type\": \"sse\"}\n }}\n";
    let fs = MemFs::new().with_file(&hermes().path, contents);
    let (servers, findings) = scan_source_with_fs(&fs, &hermes());
    assert!(findings.is_empty(), "{findings:?}");
    assert_eq!(servers.len(), 2);
    let beta = servers
        .iter()
        .find(|server| server.name == "beta")
        .expect("beta");
    assert_eq!(beta.url, "https://example.test/mcp/*x*//y");
    assert_eq!(beta.transport, "sse");
    assert_eq!(jsonc_strip("/* a */\"b\""), "\"b\"");
}

/// MCFG-001 — YAML configs normalise to the same entries.
#[test]
fn mcfg_001_yaml_normalises_string_only_fields() {
    let contents = concat!(
        "mcpServers:\n",
        "  yaml-stdio:\n",
        "    command: \"npx\"\n",
        "    args:\n",
        "      - \"-y\"\n",
        "    env:\n",
        "      QUOTED: \"1\"\n",
        "      UNQUOTED: 2\n",
    );
    let fs = MemFs::new().with_file(&hermes().path, contents);
    let (servers, findings) = scan_source_with_fs(&fs, &hermes());
    assert!(findings.is_empty(), "{findings:?}");
    assert_eq!(servers.len(), 1);
    let env = servers[0].env.clone().expect("env");
    assert_eq!(env.get("QUOTED").map(String::as_str), Some("1"));
    assert!(
        !env.contains_key("UNQUOTED"),
        "non-string values are skipped: {env:?}"
    );
    assert_eq!(servers[0].args, vec!["-y".to_owned()]);
}

/// MCFG-002 — client names, paths and root keys are exact.
#[test]
fn mcfg_002_default_source_table_and_root_key_fallback() {
    assert_eq!(normalize_key(""), vec!["mcpServers", "mcp_servers", "mcp"]);
    // The fixture files are keyed by the table's own paths, so this stays valid
    // on every platform the crate builds for.
    let sources = symaira_core_mcpcfg::default_sources_for_platform("darwin", "/home/u", None);
    let hermes_path = sources
        .iter()
        .find(|source| source.client == Client::Hermes)
        .expect("hermes source")
        .path
        .clone();
    let opencode_path = sources
        .iter()
        .find(|source| source.client == Client::OpenCode)
        .expect("opencode source")
        .path
        .clone();
    let fs = MemFs::new()
        .with_file(
            &hermes_path,
            r#"{"mcp_servers": {"a": {"command": "cmd-a"}}}"#,
        )
        .with_file(
            &opencode_path,
            r#"{"mcp": {"b": {"type": "local", "command": "cmd-b"}}}"#,
        );
    let result = scan_all_with_fs(&fs, &sources);
    assert_eq!(result.servers.len(), 2, "{:?}", result.servers);
    assert!(
        result
            .servers
            .iter()
            .any(|server| server.client == "hermes")
    );
    assert!(
        result
            .servers
            .iter()
            .any(|server| server.client == "opencode")
    );
}

/// MCFG-003 — transport resolution and env merging are exact.
#[test]
fn mcfg_003_transport_and_merged_env() {
    let contents = r#"{"mcpServers": {
        "http-url": {"url": "https://example.test/mcp"},
        "sse-type": {"url": "https://example.test/sse", "type": "sse"},
        "passthrough": {"command": "cmd-a", "transport": "SSE"},
        "env-merge": {"command": "cmd-b", "env": {"SHARED": "env", "ONLY_ENV": "1"},
                      "environment": {"SHARED": "environment", "ONLY_ENVIRONMENT": "2"}}}}"#;
    let fs = MemFs::new().with_file(&hermes().path, contents);
    let (servers, findings) = scan_source_with_fs(&fs, &hermes());
    assert!(findings.is_empty(), "{findings:?}");
    let by_name = |name: &str| {
        servers
            .iter()
            .find(|server| server.name == name)
            .expect(name)
    };
    assert_eq!(by_name("http-url").transport, "http");
    assert_eq!(by_name("sse-type").transport, "sse");
    assert_eq!(by_name("passthrough").transport, "SSE");
    let merged = by_name("env-merge").env.clone().expect("env");
    assert_eq!(merged.get("SHARED").map(String::as_str), Some("env"));
    assert_eq!(
        merged.get("ONLY_ENVIRONMENT").map(String::as_str),
        Some("2")
    );
    let mut env_keys = by_name("env-merge").env_keys.clone();
    env_keys.sort();
    assert_eq!(env_keys, vec!["ONLY_ENV", "ONLY_ENVIRONMENT", "SHARED"]);
}

/// MCFG-003 — an OpenCode entry whose `type` is neither `local` nor `remote`
/// keeps its raw transport and is reported as approximate.
#[test]
fn mcfg_003_opencode_unknown_type_keeps_raw_transport() {
    let contents = r#"{"mcp": {"sse-type": {"url": "https://example.test/sse", "type": "sse"}}}"#;
    let fs = MemFs::new().with_file(&opencode().path, contents);
    let (servers, findings) = scan_source_with_fs(&fs, &opencode());
    assert_eq!(servers.len(), 1);
    assert_eq!(servers[0].transport, "sse");
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].status, Status::Approximate);
}

/// MCFG-004 — missing, unreadable and unparseable sources yield stable findings
/// and glob expansion stays tolerant.
#[test]
fn mcfg_004_findings_and_glob_tolerance() {
    let fs = MemFs::new();
    let (servers, findings) = scan_source_with_fs(&fs, &hermes());
    assert!(servers.is_empty());
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].status, Status::Unsupported);
    assert_eq!(findings[0].message, "read failed");

    // Only `Discover` expands globs; `ScanAllWithFS` reads the pattern
    // literally, so a glob source fails to read and is reported — the same
    // behaviour the Go implementation has.
    let glob_source = ScanSource::new(Client::VSCode, "/cfg/vscode/*.json", DEFAULT_SERVERS_KEY);
    let literal = MemFs::new();
    let result = scan_all_with_fs(&literal, std::slice::from_ref(&glob_source));
    assert!(result.servers.is_empty());
    assert_eq!(result.findings.len(), 1);
    assert_eq!(result.findings[0].message, "read failed");
}

/// MCFG-004 — `Discover` expands globs against the real filesystem and tolerates
/// a pattern that matches nothing.
#[test]
fn mcfg_004_discover_expands_globs() {
    let root = std::env::temp_dir().join(format!("corekit-mcpcfg-glob-{}", std::process::id()));
    let directory = root.join("vscode");
    std::fs::create_dir_all(&directory).expect("temp dir");
    std::fs::write(
        directory.join("one.json"),
        r#"{"mcpServers": {"one": {"command": "cmd-one"}}}"#,
    )
    .expect("write one");
    std::fs::write(
        directory.join("two.json"),
        r#"{"mcpServers": {"two": {"command": "cmd-two"}}}"#,
    )
    .expect("write two");
    let pattern = format!("{}/*.json", directory.to_string_lossy());
    let (servers, notes) = discover(
        &symaira_core_mcpcfg::OsFs,
        &[ScanSource::new(
            Client::VSCode,
            pattern.clone(),
            DEFAULT_SERVERS_KEY,
        )],
    );
    assert!(notes.is_empty(), "{notes:?}");
    assert_eq!(servers.len(), 2, "{servers:?}");

    let (servers, notes) = discover(
        &symaira_core_mcpcfg::OsFs,
        &[ScanSource::new(
            Client::VSCode,
            format!("{}/*.missing", directory.to_string_lossy()),
            DEFAULT_SERVERS_KEY,
        )],
    );
    assert!(servers.is_empty() && notes.is_empty(), "no match is silent");
    let _ = std::fs::remove_dir_all(&root);
}

/// MCFG-004 — parse failures are reported with stable kinds, and `Discover`
/// tolerates a missing file without a note.
#[test]
fn mcfg_004_parse_error_kinds_and_discover_tolerance() {
    let broken = MemFs::new().with_file(&hermes().path, r#"{"mcpServers": {"#);
    let (_, findings) = scan_source_with_fs(&broken, &hermes());
    assert_eq!(findings[0].message, "parse JSON");

    let array = MemFs::new().with_file(&hermes().path, r#"{"mcpServers": [1, 2]}"#);
    let (_, findings) = scan_source_with_fs(&array, &hermes());
    assert_eq!(findings[0].message, r#"parse "mcpServers""#);

    let wrong_field =
        MemFs::new().with_file(&hermes().path, r#"{"mcpServers": {"a": {"args": "no"}}}"#);
    let (_, findings) = scan_source_with_fs(&wrong_field, &hermes());
    assert_eq!(findings[0].message, r#"parse "mcpServers""#);

    let elsewhere = MemFs::new().with_file(&hermes().path, r#"{"other": {}}"#);
    let (_, findings) = scan_source_with_fs(&elsewhere, &hermes());
    assert_eq!(findings[0].message, r#"key not found: "mcpServers""#);

    let yaml_list = MemFs::new().with_file(&hermes().path, "mcpServers:\n  - a\n");
    let (_, findings) = scan_source_with_fs(&yaml_list, &hermes());
    assert_eq!(findings[0].message, r#"key "mcpServers" is not an object"#);

    let missing = MemFs::new();
    let (servers, notes) = discover(&missing, std::slice::from_ref(&hermes()));
    assert!(
        servers.is_empty() && notes.is_empty(),
        "missing files are tolerated silently"
    );
}

/// MCFG-005 — status, approximation and messages are exact.
#[test]
fn mcfg_005_status_and_messages() {
    let contents = r#"{"mcp": {"mystery": {"type": "websocket", "command": "cmd-a"},
                                 "empty-type": {"type": "", "command": "cmd-b"}}}"#;
    let fs = MemFs::new().with_file(&opencode().path, contents);
    let (servers, findings) = scan_source_with_fs(&fs, &opencode());
    assert_eq!(servers.len(), 2);
    assert_eq!(findings.len(), 1);
    assert_eq!(findings[0].status, Status::Approximate);
    assert_eq!(
        findings[0].message,
        r#"server "mystery" has unknown type "websocket", treated as local"#
    );
    assert_eq!(
        findings[0].to_string(),
        r#"opencode (/cfg/opencode/config.json): [approximate] server "mystery" has unknown type "websocket", treated as local"#
    );

    let naked = MemFs::new().with_file(&hermes().path, r#"{"mcpServers": {"naked": {}}}"#);
    let (_, findings) = scan_source_with_fs(&naked, &hermes());
    assert_eq!(findings[0].status, Status::Unsupported);
    assert_eq!(
        findings[0].message,
        r#"server "naked" is missing both command and url"#
    );
}

/// The parse entry point is shared, so a JSONC document with a leading comment
/// takes the YAML path — the same way the Go implementation does.
#[test]
fn jsonc_leading_comment_takes_the_yaml_path() {
    let data = b"// leading\n{\"mcpServers\": {}}";
    let error =
        parse_config_file(data, &normalize_key(DEFAULT_SERVERS_KEY)).expect_err("yaml path");
    assert_eq!(error, ConfigError::ParseYaml);
}
