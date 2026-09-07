#![deny(unsafe_code)]

use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::Path;
use std::time::Duration;
use symaira_core_fs::{
    has_traversal, safe_mkdir_all, safe_remove, safe_write_file, validate_path, write_file_atomic,
};
use symaira_core_secretref::{Resolver, SecretRef, SystemCommandRunner};
use tempfile::tempdir;

const ORACLE: &str = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588";

fn outcome(result: Result<String, impl std::fmt::Display>) -> Value {
    match result {
        Ok(value) if value.is_empty() => json!({"ok": true}),
        Ok(value) => json!({"ok": true, "value": value}),
        Err(error) => json!({"ok": false, "error": classify(&error.to_string())}),
    }
}
fn classify(error: &str) -> &'static str {
    let text = error.to_ascii_lowercase();
    if text.contains("timeout") || text.contains("timed out") || text.contains("deadline") {
        "timeout"
    } else if text.contains("command could not") {
        "helper_missing"
    } else if text.contains("not set") {
        "environment_unset"
    } else if text.contains("unsupported") || text.contains("only resolvable") {
        "error"
    } else if text.contains("symlink") || text.contains("symbolic") {
        "symlink"
    } else if text.contains("is a directory")
        || text.contains("not a directory")
        || text.contains("not a regular")
    {
        "not_directory"
    } else if text.contains("no such file")
        || text.contains("cannot find the path")
        || text.contains("cannot find the file")
    {
        "not_found"
    } else if text.contains("invalid") || text.contains("empty") {
        "invalid"
    } else if text.contains("127") {
        "helper_missing"
    } else if text.contains("failed") || text.contains("status=") {
        "helper_failed"
    } else if text.contains("no credential") {
        "invalid"
    } else {
        "error"
    }
}
fn digest(data: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(data);
    h.finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}
fn map_outcomes(entries: impl IntoIterator<Item = (String, Value)>) -> Value {
    let mut map = Map::new();
    for (k, v) in entries {
        map.insert(k, v);
    }
    Value::Object(map)
}
fn main() {
    if std::env::args().nth(1).as_deref() == Some("--helper")
        || (std::env::var_os("RUST003_HELPER_MODE_FILE").is_some()
            && std::env::args().nth(1).is_some())
    {
        helper_process();
        return;
    }
    let root = tempdir().expect("tempdir");
    let base = root.path();
    let mut cases = Map::new();
    let inputs = [
        "",
        "valid/file",
        "../escape",
        "/absolute",
        r"a\..\b",
        "a//b",
        "a\nline",
        "a\0b",
        r"C:\tmp\x",
    ];
    cases.insert("FS-001".into(),json!({"outcomes":map_outcomes(inputs.iter().map(|s|(s.to_string(),json!({"ok":validate_path(s).is_ok()}))))}));
    let traversals = [
        "",
        "valid/file",
        "../escape",
        "a/../b",
        r"a\..\b",
        "a/b..",
        "..",
        "/..",
    ];
    cases.insert("FS-002".into(),json!({"outcomes":map_outcomes(traversals.iter().map(|s|(s.to_string(),json!({"ok":true,"value":has_traversal(s).to_string()}))))}));
    cases.insert("FS-003".into(), fs_atomic(base));
    cases.insert("FS-004".into(), fs_atomic_failures(base));
    cases.insert("FS-005".into(), fs_safe_write(base));
    cases.insert("FS-006".into(), fs_safe_remove(base));
    cases.insert("FS-007".into(), fs_mkdir(base));
    cases.insert("SEC-001".into(), secret_environment());
    cases.insert("SEC-002".into(), secret_success());
    cases.insert("SEC-003".into(), secret_failures());
    cases.insert("SEC-004".into(), secret_timeout());
    let keychain_failure = if cfg!(target_os = "macos") {
        set_probe_mode("failure");
        outcome(Resolver::default().resolve("keychain://svc/acct", ""))
    } else {
        outcome(SecretRef::parse("keychain://svc").map(|_| String::new()))
    };
    set_probe_mode("success");
    cases.insert(
        "SEC-005".into(),
        json!({"platform":std::env::consts::OS,"outcomes":{"resolve":outcome(Resolver::default().resolve("keychain://svc/acct", ""))}}),
    );
    let keychain_case = if cfg!(target_os = "macos") {
        json!({"platform":std::env::consts::OS,"outcomes":{"failure":keychain_failure},"sanitized":true})
    } else {
        json!({"platform":std::env::consts::OS,"outcomes":{"invalid":keychain_failure}})
    };
    cases.insert("SEC-006".into(), keychain_case);
    println!(
        "{}",
        json!({"oracle_commit":ORACLE,"native_target":format!("{}-{}",std::env::consts::OS,std::env::consts::ARCH),"cases":cases})
    );
}

fn helper_process() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if let Ok(path) = std::env::var("RUST003_HELPER_ARGV") {
        let _ = fs::write(path, serde_json::to_vec(&args).unwrap_or_default());
    }
    let mode = std::env::var("RUST003_HELPER_MODE_FILE")
        .ok()
        .and_then(|path| fs::read_to_string(path).ok())
        .unwrap_or_else(|| std::env::var("RUST003_HELPER_MODE").unwrap_or_default());
    match mode.trim() {
        "failure" => {
            eprintln!("helper leaked oracle-secret-value");
            std::process::exit(17);
        }
        "missing" => std::process::exit(127),
        "timeout" => std::thread::sleep(Duration::from_secs(2)),
        "flood" => {
            print!("{}", "x".repeat(128 * 1024));
        }
        _ => println!("oracle-secret-value"),
    }
}

fn fs_atomic(base: &Path) -> Value {
    let p = base.join("atomic/value");
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    set_private_dir(p.parent().unwrap());
    let first = write_file_atomic(&p, b"first", 0o640);
    let second = write_file_atomic(&p, b"second", 0o600);
    let data = fs::read(&p).unwrap_or_default();
    let mode = fs::metadata(&p).map(|m| mode(&m)).unwrap_or(0);
    json!({"outcomes":{"create":outcome(first.map(|_|String::new())),"overwrite":outcome(second.map(|_|String::new()))},"files":manifest(base),"bytes_sha256":digest(&data),"mode":mode})
}
fn fs_atomic_failures(base: &Path) -> Value {
    let d = base.join("atomic-failure");
    fs::create_dir_all(&d).unwrap();
    set_private_dir(&d);
    let target = d.join("target");
    fs::create_dir(&target).unwrap();
    set_private_dir(&target);
    let a = match write_file_atomic(&target, b"blocked", 0o600) {
        Ok(()) => json!({"ok": true}),
        Err(_) => json!({"ok": false, "error": "error"}),
    };
    let b = write_file_atomic(d.join("missing/value"), b"x", 0o600).map(|_| String::new());
    json!({"outcomes":{"directory":a,"missing-parent":outcome(b)},"files":manifest(&d)})
}
fn fs_safe_write(base: &Path) -> Value {
    let d = base.join("safe-write");
    fs::create_dir_all(&d).unwrap();
    set_private_dir(&d);
    let p = d.join("value");
    let a = safe_write_file(&p, b"payload", 0o600).map(|_| String::new());
    let b = safe_write_file(&p, b"updated", 0o600).map(|_| String::new());
    let dir = d.join("directory");
    fs::create_dir(&dir).unwrap();
    set_private_dir(&dir);
    let c = safe_write_file(&dir, b"blocked", 0o600).map(|_| String::new());
    let e = safe_write_file(d.join("missing/x"), b"x", 0o600).map(|_| String::new());
    let data = fs::read(&p).unwrap_or_default();
    let m = fs::metadata(&p).map(|v| mode(&v)).unwrap_or(0);
    json!({"outcomes":{"create":outcome(a),"overwrite":outcome(b),"directory":outcome(c),"missing-parent":outcome(e)},"files":manifest(&d),"bytes_sha256":digest(&data),"mode":m})
}
fn fs_safe_remove(base: &Path) -> Value {
    let d = base.join("safe-remove");
    fs::create_dir_all(&d).unwrap();
    set_private_dir(&d);
    let p = d.join("value");
    fs::write(&p, b"payload").unwrap();
    let a = safe_remove(&p).map(|_| String::new());
    let b = safe_remove(d.join("missing")).map(|_| String::new());
    let dir = d.join("directory");
    fs::create_dir(&dir).unwrap();
    set_private_dir(&dir);
    let c = safe_remove(&dir).map(|_| String::new());
    json!({"outcomes":{"regular":outcome(a),"missing":outcome(b),"directory":outcome(c)},"files":manifest(&d)})
}
fn fs_mkdir(base: &Path) -> Value {
    let d = base.join("mkdir");
    let a = safe_mkdir_all(d.join("a/b"), 0o750).map(|_| String::new());
    fs::create_dir_all(&d).unwrap();
    set_private_dir(&d);
    fs::write(d.join("file"), b"x").unwrap();
    set_private_file(&d.join("file"));
    #[cfg(not(windows))]
    let b = outcome(safe_mkdir_all(d.join("file/child"), 0o750).map(|_| String::new()));
    #[cfg(windows)]
    let b = match safe_mkdir_all(d.join("file/child"), 0o750) {
        Ok(()) => json!({"ok": true}),
        Err(_) => json!({"ok": false, "error": "error"}),
    };
    let m = fs::metadata(d.join("a/b")).map(|v| mode(&v)).unwrap_or(0);
    json!({"outcomes":{"nested":outcome(a),"file-parent":b},"files":manifest(&d),"mode":m})
}
fn manifest(root: &Path) -> Vec<Value> {
    let mut entries = Vec::new();
    fn visit(root: &Path, path: &Path, entries: &mut Vec<Value>) {
        let Ok(read_dir) = fs::read_dir(path) else {
            return;
        };
        for item in read_dir.flatten() {
            let path = item.path();
            let Ok(metadata) = fs::symlink_metadata(&path) else {
                continue;
            };
            let rel = path
                .strip_prefix(root)
                .unwrap_or(&path)
                .to_string_lossy()
                .replace('\\', "/");
            let mode_value = mode(&metadata);
            if metadata.is_dir() {
                entries.push(json!({"path":rel,"type":"dir","mode":mode_value}));
                visit(root, &path, entries);
            } else if metadata.is_file() {
                let data = fs::read(&path).unwrap_or_default();
                entries.push(json!({"path":rel,"type":"file","mode":mode_value,"size":metadata.len(),"sha256":digest(&data)}));
            }
        }
    }
    visit(root, root, &mut entries);
    entries.sort_by(|a, b| a["path"].as_str().cmp(&b["path"].as_str()));
    entries
}

#[cfg(unix)]
fn set_private_dir(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = fs::set_permissions(path, fs::Permissions::from_mode(0o700));
}
#[cfg(not(unix))]
fn set_private_dir(path: &Path) {
    let _ = path;
}
#[cfg(unix)]
fn set_private_file(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = fs::set_permissions(path, fs::Permissions::from_mode(0o600));
}
#[cfg(not(unix))]
fn set_private_file(path: &Path) {
    let _ = path;
}

#[cfg(unix)]
fn mode(m: &fs::Metadata) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    m.permissions().mode() & 0o777
}
#[cfg(not(unix))]
fn mode(_: &fs::Metadata) -> u32 {
    0
}
fn secret_environment() -> Value {
    let r = Resolver::new(SystemCommandRunner).with_environment(|n| {
        if n == "RUST003_ENV" {
            Some("fixture-value".into())
        } else {
            None
        }
    });
    json!({"outcomes":{"env":outcome(r.resolve("env://RUST003_ENV","")),"bare":outcome(r.resolve("RUST003_ENV","")),"default":outcome(r.resolve("","RUST003_ENV")),"missing":outcome(r.resolve("RUST003_MISSING","")),"empty":outcome(r.resolve("",""))}})
}
fn set_probe_mode(mode: &str) {
    if let Ok(path) = std::env::var("RUST003_HELPER_MODE_FILE") {
        let _ = fs::write(path, mode);
    }
}
fn secret_success() -> Value {
    set_probe_mode("success");
    let result = Resolver::default().resolve("symvault://secrets/api", "");
    let args: Vec<String> = std::env::var("RUST003_HELPER_ARGV")
        .ok()
        .and_then(|path| fs::read(path).ok())
        .and_then(|v| serde_json::from_slice(&v).ok())
        .unwrap_or_default();
    json!({"outcomes":{"resolve":outcome(result)},"argv":args})
}
fn secret_failures() -> Value {
    set_probe_mode("failure");
    let failure = Resolver::default().resolve("symvault://secrets/api", "");
    set_probe_mode("missing");
    let missing = Resolver::default().resolve("symvault://secrets/api", "");
    set_probe_mode("success");
    json!({"outcomes":{"failure":outcome(failure),"missing-binary":outcome(missing)},"sanitized":true})
}
fn secret_timeout() -> Value {
    set_probe_mode("timeout");
    let result = Resolver::default()
        .with_timeout(Duration::from_millis(40))
        .resolve("symvault://secrets/api", "");
    set_probe_mode("success");
    json!({"outcomes":{"deadline":outcome(result)},"sanitized":true})
}
