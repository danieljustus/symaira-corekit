use crate::extract;
use std::fs;
use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

static TEMP_ID: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone)]
pub struct Input {
    pub id: String,
    pub asset_name: String,
    pub payload_hex: String,
    pub checksum_ok: bool,
    pub initial_exists: bool,
    pub initial_content: String,
    pub initial_mode: u32,
    pub extract_binary: String,
    pub validate_error: String,
    pub use_zip: bool,
    pub omit_asset: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileObservation {
    pub path: String,
    pub content: String,
    pub mode: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Observation {
    pub error_code: String,
    pub target_exists: bool,
    pub target_content: String,
    pub target_mode: u32,
    pub backup_exists: bool,
    pub stage_during_download: bool,
    pub temp_during_download: bool,
    pub validator_saw_target: bool,
    pub validator_saw_backup: bool,
    pub validator_target_content: String,
    pub files: Vec<FileObservation>,
}

/// Replays the filesystem effects of the Go Applier from an oracle case.
pub fn replay(input: &Input) -> Observation {
    let id = TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root =
        std::env::temp_dir().join(format!("symaira-update-apply-{}-{id}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    if fs::create_dir_all(&root).is_err() {
        return empty_error("apply_failed");
    }
    let target = root.join("mytool");
    if input.initial_exists
        && (fs::write(&target, &input.initial_content).is_err()
            || set_mode(&target, input.initial_mode).is_err())
    {
        let _ = fs::remove_dir_all(&root);
        return empty_error("apply_failed");
    }

    let payload = match decode_hex(&input.payload_hex) {
        Some(bytes) => bytes,
        None => {
            let _ = fs::remove_dir_all(&root);
            return empty_error("apply_failed");
        }
    };
    let stage_seen = !input.omit_asset;
    let mut error_code = String::new();
    let mut validator_saw_target = false;
    let mut validator_saw_backup = false;
    let mut validator_target_content = String::new();

    let asset_matches = if input.omit_asset {
        false
    } else if input.use_zip {
        input.asset_name.contains("windows")
    } else {
        input.asset_name.contains("linux") && input.asset_name.contains("amd64")
    };
    if !asset_matches {
        error_code = "missing_asset".into();
    } else if !input.checksum_ok {
        error_code = "checksum_mismatch".into();
    } else {
        let mut install_bytes = payload;
        if !input.extract_binary.is_empty() {
            let kind = if input.use_zip { "zip" } else { "tar.gz" };
            let extracted = extract::observe(kind, &install_bytes, &input.extract_binary);
            if let Some(err) = extracted.error {
                error_code = match err.code.as_str() {
                    "path_traversal" => "path_traversal",
                    _ => "apply_failed",
                }
                .into();
            } else if let Some(file) = extracted
                .files
                .iter()
                .find(|file| file.path == extracted.selected_binary)
            {
                install_bytes = file.content.as_bytes().to_vec();
            } else {
                error_code = "apply_failed".into();
            }
        }
        if error_code.is_empty() {
            let staged = root.join("updateapply-replay");
            if fs::write(&staged, &install_bytes).is_err() || set_mode(&staged, 0o755).is_err() {
                error_code = "apply_failed".into();
            } else if input.initial_exists {
                if fs::rename(&target, root.join("mytool.bak")).is_err()
                    || fs::rename(&staged, &target).is_err()
                {
                    error_code = "apply_failed".into();
                }
            } else if fs::rename(&staged, &target).is_err() {
                error_code = "apply_failed".into();
            }
            if error_code.is_empty() && !input.validate_error.is_empty() {
                validator_saw_target = target.exists();
                validator_saw_backup = root.join("mytool.bak").exists();
                validator_target_content = fs::read_to_string(&target).unwrap_or_default();
                if input.initial_exists {
                    let _ = fs::remove_file(&target);
                    if fs::rename(root.join("mytool.bak"), &target).is_err() {
                        error_code = "apply_failed".into();
                    }
                } else if fs::remove_file(&target).is_err() {
                    error_code = "apply_failed".into();
                }
                if error_code.is_empty() {
                    error_code = "validation_failed".into();
                }
            } else if error_code.is_empty() && input.initial_exists {
                let _ = fs::remove_file(root.join("mytool.bak"));
            }
        }
    }

    let observation = observe(
        &root,
        &target,
        error_code,
        stage_seen,
        validator_saw_target,
        validator_saw_backup,
        validator_target_content,
    );
    let _ = fs::remove_dir_all(root);
    observation
}

fn observe(
    root: &Path,
    target: &Path,
    error_code: String,
    stage_seen: bool,
    validator_saw_target: bool,
    validator_saw_backup: bool,
    validator_target_content: String,
) -> Observation {
    let target_exists = target.exists();
    let target_content = fs::read_to_string(target).unwrap_or_default();
    let target_mode = mode(target).unwrap_or_default();
    let mut files = Vec::new();
    if target_exists {
        files.push(FileObservation {
            path: "mytool".into(),
            content: target_content.clone(),
            mode: target_mode,
        });
    }
    Observation {
        error_code,
        target_exists,
        target_content,
        target_mode,
        backup_exists: root.join("mytool.bak").exists(),
        stage_during_download: stage_seen,
        temp_during_download: false,
        validator_saw_target,
        validator_saw_backup,
        validator_target_content,
        files,
    }
}

fn empty_error(error_code: &str) -> Observation {
    Observation {
        error_code: error_code.into(),
        target_exists: false,
        target_content: String::new(),
        target_mode: 0,
        backup_exists: false,
        stage_during_download: false,
        temp_during_download: false,
        validator_saw_target: false,
        validator_saw_backup: false,
        validator_target_content: String::new(),
        files: Vec::new(),
    }
}

fn decode_hex(raw: &str) -> Option<Vec<u8>> {
    if !raw.len().is_multiple_of(2) {
        return None;
    }
    raw.as_bytes()
        .as_chunks::<2>()
        .0
        .iter()
        .map(|pair| {
            let high = (pair[0] as char).to_digit(16)?;
            let low = (pair[1] as char).to_digit(16)?;
            Some(((high << 4) | low) as u8)
        })
        .collect()
}

#[cfg(unix)]
fn set_mode(path: &Path, mode: u32) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(mode))
}

#[cfg(not(unix))]
fn set_mode(_path: &Path, _mode: u32) -> std::io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn mode(path: &Path) -> std::io::Result<u32> {
    use std::os::unix::fs::PermissionsExt;
    Ok(fs::metadata(path)?.permissions().mode() & 0o777)
}

#[cfg(not(unix))]
fn mode(_path: &Path) -> std::io::Result<u32> {
    Ok(0)
}
