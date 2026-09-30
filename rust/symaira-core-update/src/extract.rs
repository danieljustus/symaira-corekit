use cap_std::fs::{Dir, OpenOptions};
use flate2::read::GzDecoder;
use std::fs::{self, File};
use std::io::{self, Cursor, Read, Write};
use std::path::{Component, Path};
use std::sync::atomic::{AtomicU64, Ordering};

const MAX_EXTRACT_SIZE: u64 = 100 * 1024 * 1024;
static TEMP_ID: AtomicU64 = AtomicU64::new(0);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FileObservation {
    pub path: String,
    pub content: String,
    pub mode: u32,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ErrorObservation {
    pub code: String,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Observation {
    pub id: String,
    pub kind: String,
    pub archive: String,
    pub archive_sha256: String,
    pub expected_binary: String,
    pub selected_binary: String,
    pub files: Vec<FileObservation>,
    pub error: Option<ErrorObservation>,
}

#[derive(Debug)]
struct ExtractError {
    code: &'static str,
    message: String,
}

impl ExtractError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}

/// Extract the named binary into an existing, private staging directory.
/// Archive suffixes select tar.gz/tgz or ZIP; unknown suffixes probe both.
/// The returned file remains in `root` until the caller installs or removes it.
///
/// # Errors
/// Refuses traversal, malformed archives, missing binaries and oversized output.
pub fn extract_binary_to_dir(
    archive: &[u8],
    asset_name: &str,
    root: &Path,
    expected: &str,
) -> Result<std::path::PathBuf, String> {
    let name = asset_name.to_ascii_lowercase();
    let extracted = if name.ends_with(".zip") {
        extract_zip(archive, root, expected)
    } else if name.ends_with(".tar.gz") || name.ends_with(".tgz") {
        extract_tar_gz(archive, root, expected)
    } else {
        let tar = extract_tar_gz(archive, root, expected);
        match tar {
            Ok(path) => Ok(path),
            Err(error) if error.code == "path_traversal" => Err(error),
            Err(error) => match extract_zip(archive, root, expected) {
                Ok(path) => Ok(path),
                Err(_) if error.code == "binary_not_found" => Err(error),
                Err(zip_error) => Err(zip_error),
            },
        }
    }
    .map_err(|error| error.message)?;
    // Go's Apply additionally rejects a returned path containing "..".
    if extracted.contains("..") {
        return Err(format!(
            "extracted binary path {extracted:?} escapes extraction directory"
        ));
    }
    Ok(root.join(extracted))
}

/// Replays a Go archive extraction case and observes the resulting files.
pub fn observe(kind: &str, archive: &[u8], expected: &str) -> Observation {
    let id = TEMP_ID.fetch_add(1, Ordering::Relaxed);
    let root = std::env::temp_dir().join(format!(
        "symaira-update-extract-{}-{id}",
        std::process::id()
    ));
    let mut result = Observation {
        id: String::new(),
        kind: kind.to_owned(),
        archive: String::new(),
        archive_sha256: String::new(),
        expected_binary: expected.to_owned(),
        selected_binary: String::new(),
        files: Vec::new(),
        error: None,
    };
    if let Err(err) = fs::create_dir(&root) {
        result.error = Some(ErrorObservation {
            code: "io".into(),
            message: err.to_string(),
        });
        return result;
    }
    let extracted = match kind {
        "tar.gz" => extract_tar_gz(archive, &root, expected),
        "zip" => extract_zip(archive, &root, expected),
        _ => Err(ExtractError::new(
            "unsupported",
            "unsupported archive format",
        )),
    };
    match extracted {
        Ok(path) => result.selected_binary = path,
        Err(err) => {
            result.error = Some(ErrorObservation {
                code: err.code.into(),
                message: err.message,
            })
        }
    }
    if let Err(err) = observe_files(&root, &mut result.files) {
        result.error = Some(ErrorObservation {
            code: "io".into(),
            message: err.to_string(),
        });
    }
    let _ = fs::remove_dir_all(root);
    result
}

fn extract_tar_gz(data: &[u8], root: &Path, expected: &str) -> Result<String, ExtractError> {
    if !data.starts_with(&[0x1f, 0x8b]) {
        return Err(ExtractError::new(
            "invalid_gzip",
            "decompress gzip: gzip: invalid header",
        ));
    }
    let root = Dir::open_ambient_dir(root, cap_std::ambient_authority())
        .map_err(|err| ExtractError::new("io", format!("open destination directory: {err}")))?;
    let mut archive = tar::Archive::new(GzDecoder::new(Cursor::new(data)));
    let entries = archive
        .entries()
        .map_err(|err| ExtractError::new("invalid_tar", format!("read tar header: {err}")))?;
    let mut selected = None;
    let mut total = 0u64;
    for entry in entries {
        let mut entry = entry
            .map_err(|err| ExtractError::new("invalid_tar", format!("read tar header: {err}")))?;
        let raw_name = entry
            .path()
            .map_err(|err| ExtractError::new("invalid_tar", format!("read tar header: {err}")))?
            .to_string_lossy()
            .replace('\\', "/");
        let name = clean_name(&raw_name);
        validate_name(&name)?;
        let entry_type = entry.header().entry_type();
        if entry_type.is_dir() {
            root.create_dir_all(&name).map_err(|err| {
                ExtractError::new("io", format!("create directory {name:?}: {err}"))
            })?;
        } else if entry_type.is_file() {
            let path = Path::new(&name);
            if let Some(parent) = path.parent() {
                root.create_dir_all(parent).map_err(|err| {
                    ExtractError::new("io", format!("create parent dir for {name:?}: {err}"))
                })?;
            }
            let mode = entry.header().mode().unwrap_or(0o600) & 0o777;
            let mut out = open_with_mode(&root, path, mode)
                .map_err(|err| ExtractError::new("io", format!("create file {name:?}: {err}")))?;
            let mut limited = (&mut entry).take(MAX_EXTRACT_SIZE - total);
            let copied = io::copy(&mut limited, &mut out)
                .map_err(|err| ExtractError::new("io", format!("write file {name:?}: {err}")))?;
            total += copied;
            if total >= MAX_EXTRACT_SIZE {
                return Err(ExtractError::new(
                    "size_limit",
                    format!("archive exceeds maximum extraction size of {MAX_EXTRACT_SIZE} bytes"),
                ));
            }
            if Path::new(&name)
                .file_name()
                .is_some_and(|base| base == expected)
            {
                selected = Some(name);
            }
        }
    }
    selected.ok_or_else(|| {
        ExtractError::new(
            "binary_not_found",
            format!("binary not found in archive: {expected}"),
        )
    })
}

fn extract_zip(data: &[u8], root: &Path, expected: &str) -> Result<String, ExtractError> {
    let records = zip_records(data)?;
    let root = Dir::open_ambient_dir(root, cap_std::ambient_authority())
        .map_err(|err| ExtractError::new("io", format!("open destination directory: {err}")))?;
    let mut selected = None;
    let mut total = 0u64;
    for record in records {
        let name = clean_name(&record.name);
        validate_name(&name)?;
        if record.name.ends_with('/') || record.is_dir {
            root.create_dir_all(&name).map_err(|err| {
                ExtractError::new("io", format!("create directory {name:?}: {err}"))
            })?;
            continue;
        }
        let local = record.local_offset as usize;
        if read_u32(data, local) != Some(0x0403_4b50)
            || local.checked_add(30).is_none_or(|end| end > data.len())
        {
            return Err(invalid_zip());
        }
        let name_len = read_u16(data, local + 26).unwrap_or(0) as usize;
        let extra_len = read_u16(data, local + 28).unwrap_or(0) as usize;
        let start = local
            .checked_add(30 + name_len + extra_len)
            .filter(|start| *start <= data.len())
            .ok_or_else(invalid_zip)?;
        let end = start
            .checked_add(record.compressed_size as usize)
            .filter(|end| *end <= data.len())
            .ok_or_else(invalid_zip)?;
        let remaining = MAX_EXTRACT_SIZE - total;
        let body = match record.method {
            0 => data[start..end][..(end - start).min(remaining as usize)].to_vec(),
            8 => {
                let decoder = flate2::read::DeflateDecoder::new(&data[start..end]);
                let mut body = Vec::new();
                decoder
                    .take(remaining)
                    .read_to_end(&mut body)
                    .map_err(|_| invalid_zip())?;
                body
            }
            _ => return Err(invalid_zip()),
        };
        total += body.len() as u64;
        if total >= MAX_EXTRACT_SIZE {
            return Err(ExtractError::new(
                "size_limit",
                format!("archive exceeds maximum extraction size of {MAX_EXTRACT_SIZE} bytes"),
            ));
        }
        let path = Path::new(&name);
        if let Some(parent) = path.parent() {
            root.create_dir_all(parent).map_err(|err| {
                ExtractError::new("io", format!("create parent dir for {name:?}: {err}"))
            })?;
        }
        let mut out = open_with_mode(&root, path, record.mode)
            .map_err(|err| ExtractError::new("io", format!("create file {name:?}: {err}")))?;
        out.write_all(&body)
            .map_err(|err| ExtractError::new("io", format!("write file {name:?}: {err}")))?;
        if Path::new(&name)
            .file_name()
            .is_some_and(|base| base == expected)
        {
            selected = Some(name);
        }
    }
    selected.ok_or_else(|| {
        ExtractError::new(
            "binary_not_found",
            format!("binary not found in archive: {expected}"),
        )
    })
}

struct ZipRecord {
    name: String,
    method: u16,
    compressed_size: u32,
    local_offset: u32,
    mode: u32,
    is_dir: bool,
}

fn zip_records(data: &[u8]) -> Result<Vec<ZipRecord>, ExtractError> {
    let start = data.len().saturating_sub(65_557);
    let eocd = (start..data.len().saturating_sub(3))
        .rev()
        .find(|&i| read_u32(data, i) == Some(0x0605_4b50))
        .ok_or_else(invalid_zip)?;
    let count = read_u16(data, eocd + 10).ok_or_else(invalid_zip)? as usize;
    let mut offset = read_u32(data, eocd + 16).ok_or_else(invalid_zip)? as usize;
    let mut records = Vec::with_capacity(count);
    for _ in 0..count {
        if read_u32(data, offset) != Some(0x0201_4b50) || offset + 46 > data.len() {
            return Err(invalid_zip());
        }
        let name_len = read_u16(data, offset + 28).ok_or_else(invalid_zip)? as usize;
        let extra_len = read_u16(data, offset + 30).ok_or_else(invalid_zip)? as usize;
        let comment_len = read_u16(data, offset + 32).ok_or_else(invalid_zip)? as usize;
        let end = offset
            .checked_add(46 + name_len + extra_len + comment_len)
            .filter(|end| *end <= data.len())
            .ok_or_else(invalid_zip)?;
        let name = std::str::from_utf8(&data[offset + 46..offset + 46 + name_len])
            .map_err(|_| invalid_zip())?
            .to_owned();
        let attrs = read_u32(data, offset + 38).ok_or_else(invalid_zip)?;
        records.push(ZipRecord {
            name,
            method: read_u16(data, offset + 10).ok_or_else(invalid_zip)?,
            compressed_size: read_u32(data, offset + 20).ok_or_else(invalid_zip)?,
            local_offset: read_u32(data, offset + 42).ok_or_else(invalid_zip)?,
            mode: (attrs >> 16) & 0o7777,
            is_dir: attrs >> 16 & 0o170000 == 0o040000,
        });
        offset = end;
    }
    Ok(records)
}

fn invalid_zip() -> ExtractError {
    ExtractError::new("invalid_zip", "open zip archive: zip: not a valid zip file")
}

fn validate_name(name: &str) -> Result<(), ExtractError> {
    if name.is_empty()
        || name.starts_with('/')
        || Path::new(name).components().any(|part| {
            matches!(
                part,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        // Go's filepath.Clean renders the rejected path with native separators.
        #[cfg(windows)]
        let name = name.replace('/', "\\");
        return Err(ExtractError::new(
            "path_traversal",
            format!("archive entry attempts path traversal: {name:?}"),
        ));
    }
    Ok(())
}

#[cfg(all(test, windows))]
mod windows_path_tests {
    #[test]
    fn traversal_diagnostics_use_native_separators() {
        for (input, native) in [("../escape", r"..\escape"), ("/outside", r"\outside")] {
            let error = super::validate_name(input).unwrap_err();
            assert_eq!(error.code, "path_traversal");
            assert_eq!(
                error.message,
                format!("archive entry attempts path traversal: {native:?}")
            );
        }
    }

    #[test]
    fn reject_drive_relative_absolute_unc_and_device_paths() {
        for name in [
            "C:/escape",
            "C:escape",
            "//server/share/escape",
            "//?/C:/escape",
            "/escape",
        ] {
            assert!(super::validate_name(name).is_err(), "accepted {name:?}");
        }
        assert!(super::validate_name("bundle/tool.exe").is_ok());
    }
}

fn clean_name(raw: &str) -> String {
    let absolute = raw.starts_with('/');
    let mut parts = Vec::new();
    for part in raw.split('/') {
        match part {
            "" | "." => {}
            ".." if parts.last().is_some_and(|last| *last != "..") => {
                parts.pop();
            }
            ".." if !absolute => parts.push(".."),
            ".." => {}
            other => parts.push(other),
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

fn open_with_mode(root: &Dir, path: &Path, mode: u32) -> io::Result<File> {
    let mut options = OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use cap_std::fs::OpenOptionsExt;
        options.mode(mode);
    }
    #[cfg(not(unix))]
    let _ = mode;
    root.open_with(path, &options)
        .map(cap_std::fs::File::into_std)
}

fn observe_files(root: &Path, output: &mut Vec<FileObservation>) -> io::Result<()> {
    fn walk(root: &Path, dir: &Path, output: &mut Vec<FileObservation>) -> io::Result<()> {
        let mut entries = fs::read_dir(dir)?.collect::<Result<Vec<_>, _>>()?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.is_dir() {
                walk(root, &path, output)?;
            } else if metadata.is_file() {
                let content = fs::read_to_string(&path)?;
                let relative = path
                    .strip_prefix(root)
                    .unwrap_or(&path)
                    .to_string_lossy()
                    .replace('\\', "/");
                #[cfg(unix)]
                let mode = {
                    use std::os::unix::fs::PermissionsExt;
                    metadata.permissions().mode() & 0o777
                };
                #[cfg(not(unix))]
                let mode = 0;
                output.push(FileObservation {
                    path: relative,
                    content,
                    mode,
                });
            }
        }
        Ok(())
    }
    walk(root, root, output)
}

fn read_u16(data: &[u8], offset: usize) -> Option<u16> {
    Some(u16::from_le_bytes(
        data.get(offset..offset.checked_add(2)?)?.try_into().ok()?,
    ))
}

fn read_u32(data: &[u8], offset: usize) -> Option<u32> {
    Some(u32::from_le_bytes(
        data.get(offset..offset.checked_add(4)?)?.try_into().ok()?,
    ))
}
