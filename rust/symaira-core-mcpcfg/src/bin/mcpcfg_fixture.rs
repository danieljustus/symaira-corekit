//! Differential fixture: reads one corpus case from stdin and prints the
//! canonical observation JSON for this crate.
//!
//! `scripts/rust-port/mcpcfg-oracle/main.go` prints the same document from the
//! pinned Go implementation; `scripts/rust-port/mcpcfg-differential.py`
//! compares the two byte-for-byte.

use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use symaira_core_mcpcfg::{
    Client, ScanSource, Server, canonical_findings, canonical_notes, canonical_servers, clean_path,
    default_sources_for_platform, discover, scan_all_with_fs,
};

#[derive(Debug, Deserialize)]
struct CaseSource {
    client: String,
    path: String,
    #[serde(default)]
    key: String,
}

#[derive(Debug, Deserialize)]
struct Case {
    id: String,
    mode: String,
    #[serde(default)]
    goos: String,
    #[serde(default)]
    home: String,
    #[serde(default)]
    sources: Vec<CaseSource>,
    #[serde(default)]
    use_default_sources: bool,
    #[serde(default)]
    files: BTreeMap<String, String>,
}

#[derive(Debug, Serialize)]
struct SourceObs {
    client: String,
    path: String,
    key: String,
}

#[derive(Debug, Serialize)]
struct ServerObs {
    name: String,
    client: String,
    transport: String,
    command: String,
    args: Vec<String>,
    url: String,
    config_path: String,
    env: Option<BTreeMap<String, String>>,
    env_keys: Option<Vec<String>>,
    env_values: Option<Vec<String>>,
}

#[derive(Debug, Serialize)]
struct NoteObs {
    client: String,
    path: String,
    kind: String,
    message: String,
}

#[derive(Debug, Serialize)]
struct FindingObs {
    client: String,
    path: String,
    status: String,
    kind: String,
    message: String,
}

#[derive(Debug, Serialize)]
struct Observation {
    mode: String,
    default_sources: Vec<SourceObs>,
    servers: Vec<ServerObs>,
    notes: Vec<NoteObs>,
    findings: Vec<FindingObs>,
}

/// In-memory filesystem mirroring the case's `files` map, so read failures are
/// injected deterministically. Globbing always runs against the real
/// filesystem, because only `Discover` expands patterns.
struct MemFs {
    files: BTreeMap<String, String>,
}

impl symaira_core_mcpcfg::Fs for MemFs {
    fn read_file(&self, path: &str) -> std::io::Result<Vec<u8>> {
        match self.files.get(path) {
            Some(contents) => Ok(contents.as_bytes().to_vec()),
            None => Err(std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "no such file",
            )),
        }
    }

    fn glob(&self, _pattern: &str) -> std::io::Result<Vec<String>> {
        // `ScanAllWithFS` never expands globs, so the in-memory filesystem has
        // nothing to resolve; real globbing is exercised through `OsFs`.
        Ok(Vec::new())
    }
}

fn main() {
    let mut raw = String::new();
    if let Err(error) = std::io::stdin().read_to_string(&mut raw) {
        eprintln!("mcpcfg fixture: {error}");
        std::process::exit(1);
    }
    let case: Case = match serde_json::from_str(&raw) {
        Ok(case) => case,
        Err(error) => {
            eprintln!("mcpcfg fixture: invalid case: {error}");
            std::process::exit(1);
        }
    };
    let observation = match observe(&case) {
        Ok(observation) => observation,
        Err(error) => {
            eprintln!("mcpcfg fixture: {}: {error}", case.id);
            std::process::exit(1);
        }
    };
    match serde_json::to_string(&observation) {
        Ok(document) => println!("{document}"),
        Err(error) => {
            eprintln!("mcpcfg fixture: {error}");
            std::process::exit(1);
        }
    }
}

fn observe(case: &Case) -> Result<Observation, String> {
    let xdg = std::env::var("XDG_CONFIG_HOME").ok();
    let defaults = default_sources_for_platform(&case.goos, &case.home, xdg.as_deref());
    let mut observation = Observation {
        mode: case.mode.clone(),
        default_sources: Vec::new(),
        servers: Vec::new(),
        notes: Vec::new(),
        findings: Vec::new(),
    };
    if case.mode == "defaults" {
        observation.default_sources = defaults.iter().map(source_obs).collect();
        return Ok(observation);
    }
    let declared = case
        .sources
        .iter()
        .map(|source| {
            let client = Client::parse(&source.client)
                .ok_or_else(|| format!("unknown client {}", source.client))?;
            Ok(ScanSource::new(
                client,
                source.path.clone(),
                source.key.clone(),
            ))
        })
        .collect::<Result<Vec<_>, String>>()?;
    let sources = if case.use_default_sources {
        defaults
    } else {
        declared
    };
    match case.mode.as_str() {
        "scan" => {
            let fs = MemFs {
                files: case.files.clone(),
            };
            let result = scan_all_with_fs(&fs, &sources);
            observation.servers = canonical_servers(&result.servers)
                .iter()
                .map(|server| server_obs(server, true))
                .collect();
            observation.findings = canonical_findings(&result.findings)
                .iter()
                .map(|finding| FindingObs {
                    client: finding.client.as_str().to_owned(),
                    path: finding.path.clone(),
                    status: finding.status.as_str().to_owned(),
                    kind: finding_kind(&finding.message),
                    message: normalized_message(&finding.message),
                })
                .collect();
        }
        "discover" => {
            let root = temp_root(&case.id)?;
            for (path, contents) in &case.files {
                let target = rooted(&root, path);
                if let Some(parent) = target.parent() {
                    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
                }
                fs::write(&target, contents).map_err(|error| error.to_string())?;
            }
            let rewritten: Vec<ScanSource> = sources
                .iter()
                .map(|source| {
                    ScanSource::new(
                        source.client,
                        rooted(&root, &source.path).to_string_lossy().into_owned(),
                        source.key.clone(),
                    )
                })
                .collect();
            let (servers, notes) = discover(&symaira_core_mcpcfg::OsFs, &rewritten);
            observation.servers = canonical_servers(&servers)
                .iter()
                .map(|server| {
                    let mut observed = server_obs(server, false);
                    observed.config_path = strip_root(&root, &server.config_path);
                    observed
                })
                .collect();
            observation.notes = canonical_notes(&notes)
                .iter()
                .map(|note| NoteObs {
                    client: note.client.as_str().to_owned(),
                    path: strip_root(&root, &note.path),
                    kind: note.error.kind().to_owned(),
                    message: note.error.message(),
                })
                .collect();
            let _ = fs::remove_dir_all(&root);
        }
        other => return Err(format!("unknown mode {other}")),
    }
    Ok(observation)
}

fn source_obs(source: &ScanSource) -> SourceObs {
    SourceObs {
        client: source.client.as_str().to_owned(),
        path: clean_path(&source.path),
        key: source.key.clone(),
    }
}

fn server_obs(server: &Server, with_env_keys: bool) -> ServerObs {
    ServerObs {
        name: server.name.clone(),
        client: server.client.clone(),
        transport: server.transport.clone(),
        command: server.command.clone(),
        args: server.args.clone(),
        url: server.url.clone(),
        config_path: clean_path(&server.config_path),
        env: server.env.clone(),
        env_keys: if with_env_keys {
            Some(sorted_env_keys(&server.env_keys))
        } else {
            None
        },
        env_values: if with_env_keys {
            Some(sorted_env_values(&server.env_keys, &server.env_values))
        } else {
            None
        },
    }
}

/// Go builds `EnvKeys`/`EnvValues` by iterating a map, so their order is
/// unspecified; the observation layer sorts the index-aligned pairs by key
/// instead of comparing an order the Go contract never guaranteed.
fn sorted_env_keys(keys: &[String]) -> Vec<String> {
    let mut sorted = keys.to_vec();
    sorted.sort();
    sorted
}

fn sorted_env_values(keys: &[String], values: &[String]) -> Vec<String> {
    let mut pairs: Vec<(&String, &str)> = keys
        .iter()
        .enumerate()
        .map(|(index, key)| (key, values.get(index).map_or("", String::as_str)))
        .collect();
    pairs.sort_by(|left, right| left.0.cmp(right.0));
    pairs
        .into_iter()
        .map(|(_, value)| value.to_owned())
        .collect()
}

/// Classifies a `mcpcfgkit` finding message, mirroring the Go oracle helper.
fn finding_kind(message: &str) -> String {
    if message.starts_with("server ") && message.ends_with("is missing both command and url") {
        return "missing_command_and_url".to_owned();
    }
    if message.starts_with("server ") && message.contains("has unknown type ") {
        return "unknown_type".to_owned();
    }
    error_kind(message)
}

/// Classifies a `mcpcfgkit` error message into a stable kind.
fn error_kind(message: &str) -> String {
    for (prefix, kind) in [
        ("parse JSON", "parse_json"),
        ("parse YAML", "parse_yaml"),
        ("key not found: ", "key_not_found"),
        ("read failed", "read_failed"),
    ] {
        if message.starts_with(prefix) {
            return kind.to_owned();
        }
    }
    if message.starts_with("parse \"") {
        return "parse_entries".to_owned();
    }
    if message.starts_with("key \"") && message.ends_with("is not an object") {
        return "key_not_object".to_owned();
    }
    "unknown".to_owned()
}

fn normalized_message(message: &str) -> String {
    match error_kind(message).as_str() {
        "parse_json" => "parse JSON".to_owned(),
        "parse_yaml" => "parse YAML".to_owned(),
        "read_failed" => "read failed".to_owned(),
        "parse_entries" => message
            .split_once(':')
            .map(|(prefix, _)| prefix.to_owned())
            .unwrap_or_else(|| message.to_owned()),
        _ => message.to_owned(),
    }
}

fn temp_root(id: &str) -> Result<PathBuf, String> {
    let safe: String = id
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() {
                character
            } else {
                '-'
            }
        })
        .collect();
    let root = std::env::temp_dir().join(format!("corekit-mcpcfg-{safe}-{}", std::process::id()));
    fs::create_dir_all(&root).map_err(|error| error.to_string())?;
    Ok(root)
}

fn rooted(root: &Path, path: &str) -> PathBuf {
    root.join(path.trim_start_matches('/'))
}

fn strip_root(root: &Path, path: &str) -> String {
    let prefix = root.to_string_lossy().into_owned();
    clean_path(path.strip_prefix(&prefix).unwrap_or(path))
}
