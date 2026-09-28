use crate::extract;
use std::fs;
use std::path::{Path, PathBuf};
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
    pub blocked_parent: bool,
    pub nested_parent: bool,
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

/// Optional post-install validation callback.
pub type BinaryValidator<'a> = &'a mut dyn FnMut(&Path) -> Result<(), String>;

fn backup_path(target: &Path) -> PathBuf {
    let mut path = target.as_os_str().to_os_string();
    path.push(".bak");
    PathBuf::from(path)
}

/// Replace a staged binary, restoring the previous target on a failed rename
/// or rejected validation. The staged path must reside on the target filesystem.
///
/// # Errors
/// Returns a filesystem or validation error, including rollback failure.
pub fn atomic_swap(
    staged: &Path,
    target: &Path,
    mut validate: Option<BinaryValidator<'_>>,
) -> Result<(), String> {
    let backup = backup_path(target);
    let had_existing = fs::metadata(target).is_ok();
    if had_existing {
        let _ = fs::remove_file(&backup);
        fs::rename(target, &backup).map_err(|err| format!("backup current binary: {err}"))?;
    }
    if let Err(err) = fs::rename(staged, target) {
        if had_existing {
            fs::rename(&backup, target).map_err(|rollback| {
                format!("install new binary failed ({err}) and rollback failed ({rollback})")
            })?;
        }
        return Err(format!("install new binary: {err}"));
    }
    let validation_error = validate.as_mut().and_then(|check| check(target).err());
    if let Some(err) = validation_error {
        match fs::remove_file(target) {
            Ok(()) => {}
            Err(remove) if remove.kind() == std::io::ErrorKind::NotFound => {}
            Err(remove) => {
                if had_existing {
                    return Err(format!(
                        "validate installed binary failed ({err}) and rollback failed: remove failed installed binary: {remove}"
                    ));
                }
                return Err(format!(
                    "validate installed binary failed ({err}) and remove failed: {remove}"
                ));
            }
        }
        if had_existing {
            fs::rename(&backup, target).map_err(|rollback| {
                format!(
                    "validate installed binary failed ({err}) and rollback failed: restore previous binary: {rollback}"
                )
            })?;
        }
        return Err(format!("validate installed binary: {err}"));
    }
    if had_existing {
        let _ = fs::remove_file(backup);
    }
    Ok(())
}

/// Replays the filesystem effects of the Go Applier from an oracle case.
pub fn replay(input: &Input) -> Observation {
    let id = TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root =
        std::env::temp_dir().join(format!("symaira-update-apply-{}-{id}", std::process::id()));
    if fs::create_dir(&root).is_err() {
        return empty_error("apply_failed");
    }
    let target = if input.blocked_parent {
        let parent = root.join("blocked-parent");
        if fs::write(&parent, "blocker").is_err() || set_mode(&parent, 0o600).is_err() {
            let _ = fs::remove_dir_all(&root);
            return empty_error("apply_failed");
        }
        parent.join("mytool")
    } else if input.nested_parent {
        let parent = root.join("nested");
        if fs::create_dir(&parent).is_err() {
            let _ = fs::remove_dir_all(&root);
            return empty_error("apply_failed");
        }
        parent.join("mytool")
    } else {
        root.join("mytool")
    };
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
    let writable = !asset_matches || check_writable(&target).is_ok();
    let staged = target.with_file_name("updateapply-replay");
    let mut stage_seen = false;
    if !asset_matches {
        error_code = "missing_asset".into();
    } else if !writable || fs::write(&staged, &payload).is_err() {
        error_code = "apply_failed".into();
    } else {
        stage_seen = staged.exists();
        if !input.checksum_ok {
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
                if fs::write(&staged, &install_bytes).is_err() || set_mode(&staged, 0o755).is_err()
                {
                    error_code = "apply_failed".into();
                } else {
                    let mut validator = |path: &Path| {
                        validator_saw_target = path == target && path.exists();
                        validator_saw_backup = backup_path(&target).exists();
                        validator_target_content = fs::read_to_string(path).unwrap_or_default();
                        Err(input.validate_error.clone())
                    };
                    let check = if input.validate_error.is_empty() {
                        None
                    } else {
                        Some(&mut validator as &mut dyn FnMut(&Path) -> Result<(), String>)
                    };
                    if atomic_swap(&staged, &target, check).is_err() {
                        error_code = if validator_saw_target {
                            "validation_failed"
                        } else {
                            "apply_failed"
                        }
                        .into();
                    }
                }
            }
        }
    }
    let _ = fs::remove_file(staged);

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
    let mut pending = vec![root.to_path_buf()];
    while let Some(dir) = pending.pop() {
        if let Ok(entries) = fs::read_dir(dir) {
            for entry in entries.flatten() {
                let path = entry.path();
                let Ok(kind) = entry.file_type() else {
                    continue;
                };
                if kind.is_dir() {
                    pending.push(path);
                    continue;
                }
                if !kind.is_file() {
                    continue;
                }
                if let (Ok(relative), Ok(content), Ok(file_mode)) = (
                    path.strip_prefix(root),
                    fs::read_to_string(&path),
                    mode(&path),
                ) {
                    files.push(FileObservation {
                        path: relative
                            .components()
                            .map(|part| part.as_os_str().to_string_lossy())
                            .collect::<Vec<_>>()
                            .join("/"),
                        content,
                        mode: file_mode,
                    });
                }
            }
        }
    }
    files.sort_by(|a, b| a.path.cmp(&b.path));
    Observation {
        error_code,
        target_exists,
        target_content,
        target_mode,
        backup_exists: backup_path(target).exists(),
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

fn check_writable(target: &Path) -> std::io::Result<()> {
    let parent = target.parent().ok_or(std::io::ErrorKind::InvalidInput)?;
    let probe = parent.join(".updateapply-writecheck");
    let file = fs::OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(false)
        .open(&probe)?;
    drop(file);
    let _ = fs::remove_file(probe);
    if fs::metadata(target).is_ok() {
        #[cfg(unix)]
        let readonly = mode(target)? & 0o200 == 0;
        #[cfg(not(unix))]
        let readonly = fs::metadata(target)?.permissions().readonly();
        if readonly {
            return Err(std::io::ErrorKind::PermissionDenied.into());
        }
    }
    Ok(())
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
