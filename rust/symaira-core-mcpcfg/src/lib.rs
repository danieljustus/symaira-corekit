//! Client MCP configuration discovery, ported from CoreKit's Go `mcpcfgkit`.
//!
//! Contracts: `docs/rust-port/contract-matrix.json` rows `MCFG-001` … `MCFG-005`.
//! Parity is proven by `scripts/rust-port/mcpcfg-differential.py`, which runs the
//! frozen corpus in `testdata/rust-port/mcpcfg-cases.json` against the pinned Go
//! implementation (see that file's `oracle_commit`) and this crate.
//!
//! Two deliberate, behaviour-preserving departures from Go, both documented in
//! the observation layer instead of papered over:
//!
//! * `Discover` returns structured [`Note`]s where Go returns formatted strings.
//!   [`Note::message`] emits the same text Go produced.
//! * Third-party parser text is *not* part of the frozen contract: errors carry
//!   the `mcpcfgkit`-authored prefix (`parse JSON`, `parse "<key>"`, `parse YAML`,
//!   `key not found: "<key>"`, `key "<key>" is not an object`, `read failed`)
//!   while the wrapped `encoding/json` / `yaml.v3` / OS detail is elided, because
//!   that detail is library-specific and cannot be reproduced byte-for-byte.

use std::collections::BTreeMap;
use std::fmt;
use std::io;
use std::path::{Component, Path, PathBuf};

/// Fallback top-level servers key, used when a source declares no key.
pub const DEFAULT_SERVERS_KEY: &str = "mcpServers";

/// Alternate top-level keys, tried after the source's own key.
pub const ALTERNATE_SERVERS_KEYS: [&str; 3] = ["mcpServers", "mcp_servers", "mcp"];

/// How completely a client's MCP configuration source was mapped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Status {
    /// Source fully mapped to server entries.
    Exact,
    /// Source mapped with assumptions.
    Approximate,
    /// Source requires manual review.
    Manual,
    /// Source could not be mapped at all.
    Unsupported,
}

impl Status {
    /// Wire name used by Go's `Status` values.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Exact => "exact",
            Self::Approximate => "approximate",
            Self::Manual => "manual",
            Self::Unsupported => "unsupported",
        }
    }
}

impl fmt::Display for Status {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// A supported AI client application.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Client {
    /// Hermes Agent.
    Hermes,
    /// Claude Desktop.
    ClaudeDesktop,
    /// Cursor.
    Cursor,
    /// Visual Studio Code.
    VSCode,
    /// OpenCode.
    OpenCode,
}

impl Client {
    /// Every supported client, in Go's source-table order.
    pub const ALL: [Self; 5] = [
        Self::Hermes,
        Self::Cursor,
        Self::VSCode,
        Self::OpenCode,
        Self::ClaudeDesktop,
    ];

    /// Wire name used by Go's `Client` values.
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Hermes => "hermes",
            Self::ClaudeDesktop => "claude-desktop",
            Self::Cursor => "cursor",
            Self::VSCode => "vscode",
            Self::OpenCode => "opencode",
        }
    }

    /// Parses a wire name, rejecting unknown clients.
    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "hermes" => Some(Self::Hermes),
            "claude-desktop" => Some(Self::ClaudeDesktop),
            "cursor" => Some(Self::Cursor),
            "vscode" => Some(Self::VSCode),
            "opencode" => Some(Self::OpenCode),
            _ => None,
        }
    }
}

impl fmt::Display for Client {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Pairing of a client with its config path and top-level servers key.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScanSource {
    /// Owning client.
    pub client: Client,
    /// Config file path (may contain `*`, `?` or `[` for glob expansion).
    pub path: String,
    /// Top-level key holding the servers map; empty means `mcpServers`.
    pub key: String,
}

impl ScanSource {
    /// Builds a source.
    #[must_use]
    pub fn new(client: Client, path: impl Into<String>, key: impl Into<String>) -> Self {
        Self {
            client,
            path: path.into(),
            key: key.into(),
        }
    }
}

/// A source (or entry) that could not be mapped exactly.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Finding {
    /// Owning client.
    pub client: Client,
    /// Config path the finding belongs to.
    pub path: String,
    /// How completely the source was mapped.
    pub status: Status,
    /// Human-readable message.
    pub message: String,
}

impl fmt::Display for Finding {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{} ({}): [{}] {}",
            self.client, self.path, self.status, self.message
        )
    }
}

/// Failure while reading or parsing a client config file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    /// Go: `parse JSON: %w` — the document is not valid JSON/JSONC.
    ParseJson,
    /// Go: `parse %q: %w` — the servers map has the wrong shape.
    ParseEntries(String),
    /// Go: `parse YAML: %w` — the document is not valid YAML.
    ParseYaml,
    /// Go: `key not found: %q`.
    KeyNotFound(String),
    /// Go: `key %q is not an object`.
    KeyNotObject(String),
}

impl ConfigError {
    /// Stable observation kind.
    #[must_use]
    pub fn kind(&self) -> &'static str {
        match self {
            Self::ParseJson => "parse_json",
            Self::ParseEntries(_) => "parse_entries",
            Self::ParseYaml => "parse_yaml",
            Self::KeyNotFound(_) => "key_not_found",
            Self::KeyNotObject(_) => "key_not_object",
        }
    }

    /// The `mcpcfgkit`-authored message text, with third-party detail elided.
    #[must_use]
    pub fn message(&self) -> String {
        match self {
            Self::ParseJson => "parse JSON".to_owned(),
            Self::ParseEntries(key) => format!("parse {key:?}"),
            Self::ParseYaml => "parse YAML".to_owned(),
            Self::KeyNotFound(key) => format!("key not found: {key:?}"),
            Self::KeyNotObject(key) => format!("key {key:?} is not an object"),
        }
    }
}

impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message())
    }
}

impl std::error::Error for ConfigError {}

/// Note about a source that could not be read into servers.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Note {
    /// Owning client.
    pub client: Client,
    /// Config path the note belongs to.
    pub path: String,
    /// Why the source could not be parsed.
    pub error: ConfigError,
}

impl Note {
    /// Go's `Discover` note text: `"<client>: <path>: <error>"`.
    #[must_use]
    pub fn message(&self) -> String {
        format!("{}: {}: {}", self.client, self.path, self.error)
    }
}

impl fmt::Display for Note {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message())
    }
}

/// One configured MCP server entry inside a config map.
///
/// Deserialised straight out of a JSON servers map, so the JSON path is strict
/// about field types the way Go's `json.Unmarshal` into `Entry` is: an `args`
/// string is a decode error, while the YAML path filters non-strings instead.
#[derive(Debug, Clone, PartialEq, Eq, Default, serde::Deserialize)]
pub struct Entry {
    /// Launch command (stdio servers).
    #[serde(default)]
    pub command: String,
    /// Launch arguments.
    #[serde(default)]
    pub args: Vec<String>,
    /// Remote URL (http/sse servers).
    #[serde(default)]
    pub url: String,
    /// Raw `type` field.
    #[serde(default, rename = "type")]
    pub entry_type: String,
    /// Raw `transport` field.
    #[serde(default)]
    pub transport: String,
    /// `env` map.
    #[serde(default)]
    pub env: Option<BTreeMap<String, String>>,
    /// OpenCode's alternative env key, `environment`.
    #[serde(default)]
    pub environment: Option<BTreeMap<String, String>>,
}

impl Entry {
    /// Effective transport, mirroring Go's `TransportValue`.
    ///
    /// OpenCode's `local`/`remote` types map to `stdio`/`http`; a non-empty
    /// `url` yields the raw `type` when set and `http` otherwise; `transport`
    /// is passed through verbatim.
    #[must_use]
    pub fn transport_value(&self) -> String {
        match self.entry_type.to_lowercase().as_str() {
            "local" => "stdio".to_owned(),
            "remote" => "http".to_owned(),
            _ => {
                if !self.url.is_empty() {
                    if self.entry_type.is_empty() {
                        "http".to_owned()
                    } else {
                        self.entry_type.clone()
                    }
                } else if !self.transport.is_empty() {
                    self.transport.clone()
                } else {
                    "stdio".to_owned()
                }
            }
        }
    }

    /// Launch command for stdio servers or URL for remote ones.
    #[must_use]
    pub fn command_or_url(&self) -> &str {
        if self.command.is_empty() {
            &self.url
        } else {
            &self.command
        }
    }

    /// `env` merged with `environment`.
    ///
    /// Go's `MergedEnv` applies `environment` first and `env` second, so `env`
    /// wins on conflicts despite the Go doc comment claiming the opposite. The
    /// port follows the code, not the comment.
    #[must_use]
    pub fn merged_env(&self) -> Option<BTreeMap<String, String>> {
        let env_empty = self.env.as_ref().is_none_or(BTreeMap::is_empty);
        let environment_empty = self.environment.as_ref().is_none_or(BTreeMap::is_empty);
        if env_empty && environment_empty {
            return None;
        }
        let mut out = self.environment.clone().unwrap_or_default();
        out.extend(self.env.clone().unwrap_or_default());
        Some(out)
    }
}

/// One configured MCP server, normalised across clients.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct Server {
    /// Server name from the config map.
    pub name: String,
    /// Owning client wire name.
    pub client: String,
    /// Effective transport.
    pub transport: String,
    /// Launch command.
    pub command: String,
    /// Launch arguments.
    pub args: Vec<String>,
    /// Remote URL.
    pub url: String,
    /// Path of the config file the server was found in.
    pub config_path: String,
    /// Effective environment.
    pub env: Option<BTreeMap<String, String>>,
    /// Environment keys, split out so callers can redact values.
    pub env_keys: Vec<String>,
    /// Environment values, index-aligned with [`Server::env_keys`].
    pub env_values: Vec<String>,
}

/// Outcome of a scan: normalised servers plus findings for whatever failed.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ScanResult {
    /// Successfully mapped servers.
    pub servers: Vec<Server>,
    /// One finding per source or entry that could not be mapped.
    pub findings: Vec<Finding>,
}

/// Filesystem abstraction so fixtures can be injected without touching real
/// client configs.
pub trait Fs {
    /// Reads a config file.
    ///
    /// # Errors
    ///
    /// Propagates the underlying I/O failure.
    fn read_file(&self, path: &str) -> io::Result<Vec<u8>>;

    /// Expands a glob pattern into matching paths.
    ///
    /// # Errors
    ///
    /// Propagates pattern or I/O failures; callers treat any error as "no
    /// matches", exactly like Go's `discoverWith`.
    fn glob(&self, pattern: &str) -> io::Result<Vec<String>>;
}

/// Real filesystem implementation.
#[derive(Debug, Clone, Copy, Default)]
pub struct OsFs;

impl Fs for OsFs {
    fn read_file(&self, path: &str) -> io::Result<Vec<u8>> {
        std::fs::read(path)
    }

    fn glob(&self, pattern: &str) -> io::Result<Vec<String>> {
        glob_paths(pattern)
    }
}

/// Expands a `*`/`?`/`[...]` pattern against the real filesystem.
///
/// Mirrors Go's `filepath.Glob` for the patterns MCP client paths use: one
/// `read_dir` per path segment, sorted results, no match is not an error.
fn glob_paths(pattern: &str) -> io::Result<Vec<String>> {
    let mut paths: Vec<PathBuf> = if pattern.starts_with('/') {
        vec![PathBuf::from("/")]
    } else {
        vec![PathBuf::new()]
    };
    for segment in pattern.split('/') {
        if segment.is_empty() {
            continue;
        }
        let mut next = Vec::new();
        if has_meta(segment) {
            for base in &paths {
                let directory = if base.as_os_str().is_empty() {
                    PathBuf::from(".")
                } else {
                    base.clone()
                };
                let Ok(entries) = std::fs::read_dir(&directory) else {
                    continue;
                };
                for entry in entries.flatten() {
                    let name = entry.file_name().to_string_lossy().into_owned();
                    if match_segment(segment, &name) {
                        next.push(entry.path());
                    }
                }
            }
        } else {
            for base in &paths {
                next.push(base.join(segment));
            }
        }
        next.sort();
        paths = next;
    }
    Ok(paths
        .into_iter()
        .filter(|path| path.exists())
        .map(|path| path.to_string_lossy().into_owned())
        .collect())
}

/// Reports whether a segment contains glob metacharacters.
fn has_meta(segment: &str) -> bool {
    segment.contains(['*', '?', '['])
}

/// Matches one path segment against a glob pattern, following Go's
/// `filepath.Match` semantics for `*`, `?`, `[...]` (with `^`/`!` negation and
/// `\` escapes).
fn match_segment(pattern: &str, name: &str) -> bool {
    let pattern: Vec<char> = pattern.chars().collect();
    let name: Vec<char> = name.chars().collect();
    match_from(&pattern, &name)
}

fn match_from(pattern: &[char], name: &[char]) -> bool {
    if pattern.is_empty() {
        return name.is_empty();
    }
    match pattern[0] {
        '*' => {
            let rest = &pattern[1..];
            (0..=name.len()).any(|skip| match_from(rest, &name[skip..]))
        }
        '?' => !name.is_empty() && match_from(&pattern[1..], &name[1..]),
        '[' => {
            let Some((class, rest)) = parse_class(&pattern[1..]) else {
                return !name.is_empty() && name[0] == '[' && match_from(&pattern[1..], &name[1..]);
            };
            if name.is_empty() {
                return false;
            }
            class_matches(&class, name[0]) && match_from(rest, &name[1..])
        }
        '\\' if pattern.len() > 1 => {
            !name.is_empty() && name[0] == pattern[1] && match_from(&pattern[2..], &name[1..])
        }
        literal => !name.is_empty() && name[0] == literal && match_from(&pattern[1..], &name[1..]),
    }
}

struct CharClass {
    negated: bool,
    items: Vec<ClassItem>,
}

enum ClassItem {
    Char(char),
    Range(char, char),
}

fn parse_class(pattern: &[char]) -> Option<(CharClass, &[char])> {
    let mut index = 0;
    let mut negated = false;
    if matches!(pattern.first(), Some('^' | '!')) {
        negated = true;
        index = 1;
    }
    let mut items = Vec::new();
    let mut first = true;
    while index < pattern.len() {
        let current = pattern[index];
        if current == ']' && !first {
            return Some((CharClass { negated, items }, &pattern[index + 1..]));
        }
        first = false;
        if pattern.get(index + 1) == Some(&'-') && pattern.get(index + 2).is_some_and(|c| *c != ']')
        {
            let (from, to) = (current, pattern[index + 2]);
            items.push(ClassItem::Range(from, to));
            index += 3;
        } else if current == '\\' && pattern.get(index + 1).is_some() {
            items.push(ClassItem::Char(pattern[index + 1]));
            index += 2;
        } else {
            items.push(ClassItem::Char(current));
            index += 1;
        }
    }
    None
}

fn class_matches(class: &CharClass, candidate: char) -> bool {
    let hit = class.items.iter().any(|item| match item {
        ClassItem::Char(value) => *value == candidate,
        ClassItem::Range(from, to) => (*from..=*to).contains(&candidate),
    });
    hit != class.negated
}

/// Normalises the user's home directory the way Go's `homeDir` does, falling
/// back to `HOME` and finally `.` (matching Go's best-effort behaviour).
#[must_use]
pub fn home_dir() -> String {
    if let Some(home) = std::env::var_os("HOME")
        && !home.is_empty()
    {
        return home.to_string_lossy().into_owned();
    }
    ".".to_owned()
}

/// Well-known client config locations for the current platform and user.
#[must_use]
pub fn default_sources() -> Vec<ScanSource> {
    default_sources_for_platform(
        std::env::consts::OS,
        &home_dir(),
        std::env::var("XDG_CONFIG_HOME").ok().as_deref(),
    )
}

/// Injectable variant of [`default_sources`] so consumers can resolve
/// platform-specific paths deterministically on any host.
///
/// `xdg_config_home` mirrors Go reading `XDG_CONFIG_HOME` from the process
/// environment inside `defaultSourcesForPlatform`; pass it explicitly to keep
/// the table deterministic.
#[must_use]
pub fn default_sources_for_platform(
    goos: &str,
    home: &str,
    xdg_config_home: Option<&str>,
) -> Vec<ScanSource> {
    let mut sources = vec![
        ScanSource::new(
            Client::Hermes,
            join(home, &[".config", "hermes", "config.json"]),
            "mcpServers",
        ),
        ScanSource::new(
            Client::Cursor,
            join(home, &[".cursor", "mcp.json"]),
            "mcpServers",
        ),
        ScanSource::new(
            Client::VSCode,
            join(home, &[".vscode", "mcp.json"]),
            "mcpServers",
        ),
        ScanSource::new(
            Client::OpenCode,
            join(home, &[".config", "opencode", "config.json"]),
            "mcp",
        ),
    ];
    if goos == "darwin" {
        sources.push(ScanSource::new(
            Client::ClaudeDesktop,
            join(
                home,
                &[
                    "Library",
                    "Application Support",
                    "Claude",
                    "claude_desktop_config.json",
                ],
            ),
            "mcpServers",
        ));
    } else {
        let xdg = match xdg_config_home {
            Some(value) if !value.is_empty() => value.to_owned(),
            _ => join(home, &[".config"]),
        };
        sources.push(ScanSource::new(
            Client::ClaudeDesktop,
            join(&xdg, &["claude", "claude_desktop_config.json"]),
            "mcpServers",
        ));
    }
    sources
}

fn join(base: &str, parts: &[&str]) -> String {
    let mut path = Path::new(base).to_path_buf();
    for part in parts {
        path.push(part);
    }
    normalise(&path)
}

/// Renders a path the way Go's `filepath.Join` does, keeping a leading `/`.
fn normalise(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

/// Removes `//` line comments and `/* */` block comments from JSONC text while
/// preserving strings and their escapes, so URLs survive.
#[must_use]
pub fn jsonc_strip(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    let runes: Vec<char> = input.chars().collect();
    let mut index = 0;
    let mut in_string = false;
    let mut escaped = false;
    while index < runes.len() {
        let current = runes[index];
        if in_string {
            out.push(current);
            if escaped {
                escaped = false;
            } else if current == '\\' {
                escaped = true;
            } else if current == '"' {
                in_string = false;
            }
            index += 1;
            continue;
        }
        if current == '"' {
            in_string = true;
            out.push(current);
            index += 1;
            continue;
        }
        if current == '/' && index + 1 < runes.len() {
            match runes[index + 1] {
                '/' => {
                    while index < runes.len() && runes[index] != '\n' {
                        index += 1;
                    }
                    continue;
                }
                '*' => {
                    index += 2;
                    while index + 1 < runes.len()
                        && !(runes[index] == '*' && runes[index + 1] == '/')
                    {
                        index += 1;
                    }
                    index += 2;
                    continue;
                }
                _ => {}
            }
        }
        out.push(current);
        index += 1;
    }
    out
}

/// Fallback candidate list for a source key: the explicit key (or `mcpServers`)
/// first, then the known alternates.
#[must_use]
pub fn normalize_key(key: &str) -> Vec<String> {
    let key = if key.is_empty() {
        DEFAULT_SERVERS_KEY
    } else {
        key
    };
    let mut candidates = vec![key.to_owned()];
    for alternate in ALTERNATE_SERVERS_KEYS {
        if alternate != key {
            candidates.push(alternate.to_owned());
        }
    }
    candidates
}

/// Discovers servers from the given sources, tolerating missing files and
/// reporting parse failures as notes.
#[must_use]
pub fn discover<F: Fs>(fs: &F, sources: &[ScanSource]) -> (Vec<Server>, Vec<Note>) {
    let mut servers = Vec::new();
    let mut notes = Vec::new();
    for source in sources {
        for expanded in expand_glob(fs, source) {
            let Ok(data) = fs.read_file(&expanded.path) else {
                continue;
            };
            match parse_config_file(&data, &normalize_key(&expanded.key)) {
                Ok(entries) => {
                    for (name, entry) in entries {
                        servers.push(server_from_entry(
                            &name,
                            expanded.client.as_str(),
                            &expanded.path,
                            &entry,
                        ));
                    }
                }
                Err(error) => notes.push(Note {
                    client: expanded.client,
                    path: expanded.path,
                    error,
                }),
            }
        }
    }
    (servers, notes)
}

/// Scans the current user's well-known clients.
#[must_use]
pub fn scan_all() -> ScanResult {
    scan_all_with_fs(&OsFs, &default_sources())
}

/// Scans every client source, reporting missing, unreadable and unparseable
/// sources as findings instead of skipping them silently.
#[must_use]
pub fn scan_all_with_fs<F: Fs>(fs: &F, sources: &[ScanSource]) -> ScanResult {
    let mut result = ScanResult::default();
    for source in sources {
        let (servers, findings) = scan_source_with_fs(fs, source);
        result.servers.extend(servers);
        result.findings.extend(findings);
    }
    result
}

/// Scans a single source.
#[must_use]
pub fn scan_source_with_fs<F: Fs>(fs: &F, source: &ScanSource) -> (Vec<Server>, Vec<Finding>) {
    let Ok(data) = fs.read_file(&source.path) else {
        return (
            Vec::new(),
            vec![Finding {
                client: source.client,
                path: source.path.clone(),
                status: Status::Unsupported,
                message: "read failed".to_owned(),
            }],
        );
    };
    let entries = match parse_config_file(&data, &normalize_key(&source.key)) {
        Ok(entries) => entries,
        Err(error) => {
            return (
                Vec::new(),
                vec![Finding {
                    client: source.client,
                    path: source.path.clone(),
                    status: Status::Unsupported,
                    message: error.message(),
                }],
            );
        }
    };
    let is_opencode = source.client == Client::OpenCode;
    let mut servers = Vec::new();
    let mut findings = Vec::new();
    for (name, entry) in entries {
        let command = entry.command_or_url().to_owned();
        if command.is_empty() {
            findings.push(Finding {
                client: source.client,
                path: source.path.clone(),
                status: Status::Unsupported,
                message: format!("server {name:?} is missing both command and url"),
            });
            continue;
        }
        let lowered = entry.entry_type.to_lowercase();
        if is_opencode && !entry.entry_type.is_empty() && lowered != "local" && lowered != "remote"
        {
            findings.push(Finding {
                client: source.client,
                path: source.path.clone(),
                status: Status::Approximate,
                message: format!(
                    "server {name:?} has unknown type {:?}, treated as local",
                    entry.entry_type
                ),
            });
        }
        let env = entry.merged_env();
        let mut server = Server {
            name,
            client: source.client.as_str().to_owned(),
            transport: entry.transport_value(),
            command,
            args: entry.args.clone(),
            url: entry.url.clone(),
            config_path: source.path.clone(),
            env: env.clone(),
            env_keys: Vec::new(),
            env_values: Vec::new(),
        };
        if let Some(env) = env {
            for (key, value) in env {
                server.env_keys.push(key);
                server.env_values.push(value);
            }
        }
        servers.push(server);
    }
    (servers, findings)
}

/// Builds the public server record from a parsed entry.
fn server_from_entry(name: &str, client: &str, config_path: &str, entry: &Entry) -> Server {
    Server {
        name: name.to_owned(),
        client: client.to_owned(),
        transport: entry.transport_value(),
        command: entry.command.clone(),
        args: entry.args.clone(),
        url: entry.url.clone(),
        config_path: config_path.to_owned(),
        env: entry.merged_env(),
        env_keys: Vec::new(),
        env_values: Vec::new(),
    }
}

/// Expands a source whose path contains glob metacharacters.
fn expand_glob<F: Fs>(fs: &F, source: &ScanSource) -> Vec<ScanSource> {
    if !source.path.contains(['*', '?', '[']) {
        return vec![source.clone()];
    }
    match fs.glob(&source.path) {
        Ok(matches) if !matches.is_empty() => matches
            .into_iter()
            .map(|path| ScanSource {
                client: source.client,
                path,
                key: source.key.clone(),
            })
            .collect(),
        _ => Vec::new(),
    }
}

/// Parses JSONC/JSON/YAML data into entries using the first matching key.
///
/// # Errors
///
/// Returns the [`ConfigError`] Go's `parseConfigFile` would report, with
/// third-party parser detail elided.
pub fn parse_config_file(
    data: &[u8],
    candidates: &[String],
) -> Result<BTreeMap<String, Entry>, ConfigError> {
    let text = String::from_utf8_lossy(data);
    if text.trim_start().starts_with('{') {
        match parse_json_config(&text, candidates) {
            Ok(entries) => return Ok(entries),
            Err(error) => {
                if !matches!(error, ConfigError::KeyNotFound(_)) {
                    return Err(error);
                }
            }
        }
    }
    parse_yaml_config(&text, candidates)
}

fn parse_json_config(
    text: &str,
    candidates: &[String],
) -> Result<BTreeMap<String, Entry>, ConfigError> {
    let stripped = jsonc_strip(text);
    let document: BTreeMap<String, serde_json::Value> =
        serde_json::from_str(&stripped).map_err(|_| ConfigError::ParseJson)?;
    let key = candidates
        .iter()
        .find(|candidate| document.contains_key(*candidate))
        .ok_or_else(|| ConfigError::KeyNotFound(candidates.first().cloned().unwrap_or_default()))?;
    let raw = document
        .get(key)
        .cloned()
        .unwrap_or(serde_json::Value::Null);
    let entries: BTreeMap<String, Entry> =
        serde_json::from_value(raw).map_err(|_| ConfigError::ParseEntries(key.clone()))?;
    Ok(entries)
}

/// YAML value subset the MCP config contract needs.
#[derive(Debug, Clone, PartialEq)]
enum YamlValue {
    Str(String),
    Map(BTreeMap<String, YamlValue>),
    Seq(Vec<YamlValue>),
    Other,
}

fn parse_yaml_config(
    text: &str,
    candidates: &[String],
) -> Result<BTreeMap<String, Entry>, ConfigError> {
    let documents =
        yaml_rust2::YamlLoader::load_from_str(text).map_err(|_| ConfigError::ParseYaml)?;
    let Some(document) = documents.first() else {
        return Err(ConfigError::ParseYaml);
    };
    let YamlValue::Map(document) = convert_yaml(document)? else {
        return Err(ConfigError::ParseYaml);
    };
    let key = candidates
        .iter()
        .find(|candidate| document.contains_key(*candidate))
        .ok_or_else(|| ConfigError::KeyNotFound(candidates.first().cloned().unwrap_or_default()))?;
    let Some(YamlValue::Map(raw)) = document.get(key) else {
        return Err(ConfigError::KeyNotObject(key.clone()));
    };
    let mut entries = BTreeMap::new();
    for (name, value) in raw {
        if let Some(entry) = entry_from_yaml(value) {
            entries.insert(name.clone(), entry);
        }
    }
    Ok(entries)
}

fn convert_yaml(value: &yaml_rust2::Yaml) -> Result<YamlValue, ConfigError> {
    use yaml_rust2::Yaml;
    Ok(match value {
        Yaml::String(text) => YamlValue::Str(text.clone()),
        Yaml::Integer(_) | Yaml::Real(_) | Yaml::Boolean(_) | Yaml::Null => YamlValue::Other,
        Yaml::Array(items) => YamlValue::Seq(
            items
                .iter()
                .map(convert_yaml)
                .collect::<Result<Vec<_>, _>>()?,
        ),
        Yaml::Hash(map) => {
            let mut out = BTreeMap::new();
            for (key, item) in map {
                let Yaml::String(name) = key else {
                    return Err(ConfigError::ParseYaml);
                };
                out.insert(name.clone(), convert_yaml(item)?);
            }
            YamlValue::Map(out)
        }
        Yaml::Alias(_) | Yaml::BadValue => return Err(ConfigError::ParseYaml),
    })
}

/// Converts a YAML server entry, ignoring values that are not strings —
/// mirroring Go's `entryFromYAML`, which skips malformed entries entirely.
fn entry_from_yaml(value: &YamlValue) -> Option<Entry> {
    let YamlValue::Map(map) = value else {
        return None;
    };
    let mut entry = Entry::default();
    if let Some(YamlValue::Str(command)) = map.get("command") {
        entry.command.clone_from(command);
    }
    if let Some(YamlValue::Seq(args)) = map.get("args") {
        entry.args = args
            .iter()
            .filter_map(|item| match item {
                YamlValue::Str(text) => Some(text.clone()),
                _ => None,
            })
            .collect();
    }
    if let Some(YamlValue::Str(url)) = map.get("url") {
        entry.url.clone_from(url);
    }
    if let Some(YamlValue::Str(value)) = map.get("type") {
        entry.entry_type.clone_from(value);
    }
    if let Some(YamlValue::Str(value)) = map.get("transport") {
        entry.transport.clone_from(value);
    }
    if let Some(YamlValue::Map(env)) = map.get("env") {
        entry.env = Some(string_map(env));
    }
    if let Some(YamlValue::Map(environment)) = map.get("environment") {
        entry.environment = Some(string_map(environment));
    }
    Some(entry)
}

fn string_map(map: &BTreeMap<String, YamlValue>) -> BTreeMap<String, String> {
    map.iter()
        .filter_map(|(key, value)| match value {
            YamlValue::Str(text) => Some((key.clone(), text.clone())),
            _ => None,
        })
        .collect()
}

/// Canonical ordering used by the differential observation layer, so the
/// unspecified Go map iteration order cannot make a comparison flaky.
#[must_use]
pub fn canonical_servers(servers: &[Server]) -> Vec<Server> {
    let mut sorted = servers.to_vec();
    sorted.sort_by(|left, right| {
        (&left.config_path, &left.client, &left.name).cmp(&(
            &right.config_path,
            &right.client,
            &right.name,
        ))
    });
    sorted
}

/// Canonical ordering for findings; see [`canonical_servers`].
///
/// Sorting uses the status *wire string*, not the enum order, so it matches the
/// Go oracle helper exactly.
#[must_use]
pub fn canonical_findings(findings: &[Finding]) -> Vec<Finding> {
    let mut sorted = findings.to_vec();
    sorted.sort_by(|left, right| {
        (&left.path, left.status.as_str(), &left.message).cmp(&(
            &right.path,
            right.status.as_str(),
            &right.message,
        ))
    });
    sorted
}

/// Canonical ordering for notes; see [`canonical_servers`].
#[must_use]
pub fn canonical_notes(notes: &[Note]) -> Vec<Note> {
    let mut sorted = notes.to_vec();
    sorted.sort_by(|left, right| {
        (&left.path, &left.error.kind()).cmp(&(&right.path, &right.error.kind()))
    });
    sorted
}

/// Lexically normalises a path the way Go's `filepath.Clean` does: drops `.`
/// components, resolves `..` against a preceding element, collapses repeated
/// separators and keeps a leading `/`.
#[must_use]
pub fn clean_path(path: &str) -> String {
    let absolute = path.starts_with('/');
    let mut parts: Vec<String> = Vec::new();
    for component in Path::new(path).components() {
        match component {
            Component::CurDir | Component::RootDir | Component::Prefix(_) => {}
            Component::ParentDir => match parts.last() {
                Some(last) if last != ".." => {
                    parts.pop();
                }
                Some(_) if !absolute => parts.push("..".to_owned()),
                Some(_) => {}
                None if !absolute => parts.push("..".to_owned()),
                None => {}
            },
            Component::Normal(part) => parts.push(part.to_string_lossy().into_owned()),
        }
    }
    let joined = parts.join("/");
    if absolute {
        format!("/{joined}")
    } else if joined.is_empty() {
        ".".to_owned()
    } else {
        joined
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn jsonc_keeps_urls_and_strips_comments() {
        let input = "{\n  // line\n  \"url\": \"https://x/*y*/\", /* block */ \"a\": \"//b\"\n}";
        let stripped = jsonc_strip(input);
        assert!(stripped.contains("\"url\": \"https://x/*y*/\""));
        assert!(stripped.contains("\"a\": \"//b\""));
        assert!(!stripped.contains("line"));
    }

    #[test]
    fn transport_value_follows_go_branches() {
        let local = Entry {
            entry_type: "LOCAL".to_owned(),
            ..Entry::default()
        };
        assert_eq!(local.transport_value(), "stdio");
        let remote = Entry {
            entry_type: "remote".to_owned(),
            ..Entry::default()
        };
        assert_eq!(remote.transport_value(), "http");
        let url_with_type = Entry {
            url: "https://example.test/mcp".to_owned(),
            entry_type: "sse".to_owned(),
            ..Entry::default()
        };
        assert_eq!(url_with_type.transport_value(), "sse");
        let url_only = Entry {
            url: "https://example.test/mcp".to_owned(),
            ..Entry::default()
        };
        assert_eq!(url_only.transport_value(), "http");
        let passthrough = Entry {
            transport: "SSE".to_owned(),
            ..Entry::default()
        };
        assert_eq!(passthrough.transport_value(), "SSE");
        assert_eq!(Entry::default().transport_value(), "stdio");
    }

    #[test]
    fn merged_env_lets_env_win() {
        let entry = Entry {
            env: Some(BTreeMap::from([("A".to_owned(), "env".to_owned())])),
            environment: Some(BTreeMap::from([
                ("A".to_owned(), "environment".to_owned()),
                ("B".to_owned(), "environment".to_owned()),
            ])),
            ..Entry::default()
        };
        let merged = entry.merged_env().expect("merged");
        assert_eq!(merged.get("A").map(String::as_str), Some("env"));
        assert_eq!(merged.get("B").map(String::as_str), Some("environment"));
        assert!(Entry::default().merged_env().is_none());
    }

    #[test]
    fn default_sources_platform_table_matches_go() {
        // Expectations are built with the same separator rules as the table, so
        // this holds on every platform the crate builds for.
        let claude_darwin = Path::new("/home/u")
            .join("Library")
            .join("Application Support")
            .join("Claude")
            .join("claude_desktop_config.json")
            .to_string_lossy()
            .into_owned();
        let claude_xdg = Path::new("/xdg")
            .join("claude")
            .join("claude_desktop_config.json")
            .to_string_lossy()
            .into_owned();
        let claude_fallback = Path::new("/home/u")
            .join(".config")
            .join("claude")
            .join("claude_desktop_config.json")
            .to_string_lossy()
            .into_owned();
        let darwin = default_sources_for_platform("darwin", "/home/u", None);
        assert_eq!(darwin.len(), 5);
        assert_eq!(darwin[4].path, claude_darwin);
        assert_eq!(darwin[3].key, "mcp");
        let linux = default_sources_for_platform("linux", "/home/u", Some("/xdg"));
        assert_eq!(linux[4].path, claude_xdg);
        let fallback = default_sources_for_platform("linux", "/home/u", None);
        assert_eq!(fallback[4].path, claude_fallback);
        let empty = default_sources_for_platform("linux", "/home/u", Some(""));
        assert_eq!(empty[4].path, claude_fallback);
    }

    #[test]
    fn glob_matching_rules() {
        assert!(match_segment("*.json", "mcp.json"));
        assert!(match_segment("*", ".hidden"));
        assert!(!match_segment("*.json", "mcp.yaml"));
        assert!(match_segment("[a-c]x", "bx"));
        assert!(!match_segment("[!a-c]x", "bx"));
        assert!(match_segment("a?c", "abc"));
        assert!(!match_segment("a?c", "ac"));
    }

    #[test]
    fn normalize_key_prefers_explicit_then_alternates() {
        assert_eq!(normalize_key(""), vec!["mcpServers", "mcp_servers", "mcp"]);
        assert_eq!(
            normalize_key("mcp"),
            vec!["mcp", "mcpServers", "mcp_servers"]
        );
    }

    #[test]
    fn clean_path_follows_filepath_clean() {
        assert_eq!(clean_path("/a/./b/../c"), "/a/c");
        assert_eq!(clean_path("/../a"), "/a");
        assert_eq!(clean_path("a/b"), "a/b");
        assert_eq!(clean_path("../a"), "../a");
        assert_eq!(clean_path("/a//b/"), "/a/b");
        assert_eq!(clean_path(""), ".");
    }
}
