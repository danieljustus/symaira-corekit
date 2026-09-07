#![deny(unsafe_code)]
#![allow(clippy::useless_conversion, clippy::needless_return)]

//! Capability-scoped filesystem primitives.
//!
//! Security-sensitive mutations acquire the containing directory once and use
//! handle-relative operations. On Unix this uses `openat(2)` with
//! `O_NOFOLLOW`; on platforms without an equivalent primitive the operation
//! fails closed rather than pretending that a path check is a guarantee.

use fs2::FileExt;
use std::fs;
use std::fs::File;
use std::io;
#[cfg(unix)]
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};
use thiserror::Error;

#[cfg(unix)]
use rustix::fs::{AtFlags, Mode, OFlags, fchmod, open, openat, renameat, statat, unlinkat};

static TEMP_COUNTER: AtomicU64 = AtomicU64::new(0);
pub const ORACLE_COMMIT: &str = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588";

#[derive(Debug, Error)]
pub enum FsError {
    #[error("invalid path: {0}")]
    InvalidPath(String),
    #[error("path component is a symlink: {0}")]
    Symlink(PathBuf),
    #[error("path is not a regular file: {0}")]
    NotRegular(PathBuf),
    #[error("path is not a directory: {0}")]
    NotDirectory(PathBuf),
    #[error("directory is not secure: {0}")]
    InsecureDirectory(PathBuf),
    #[error("operation is not secure on this platform: {0}")]
    UnsupportedSecurity(String),
    #[error("atomic operation failed for {path}: {source}")]
    Atomic {
        path: PathBuf,
        #[source]
        source: io::Error,
    },
    #[error("{0}")]
    Io(#[from] io::Error),
}

pub fn validate_path(path: &str) -> Result<(), FsError> {
    if path.is_empty() {
        return Err(FsError::InvalidPath("path is empty".into()));
    }
    if path.as_bytes().contains(&0) {
        return Err(FsError::InvalidPath("path contains null byte".into()));
    }
    if let Some(control) = path.chars().find(|c| c.is_control()) {
        return Err(FsError::InvalidPath(format!(
            "path contains control character 0x{:02x}",
            control as u32
        )));
    }
    // Go first normalizes backslashes on every platform, then applies the
    // target-native filepath normalization.
    let normalized = path.replace('\\', "/");
    if normalized.starts_with('/') {
        return Err(FsError::InvalidPath("path must be relative".into()));
    }
    let segments: Vec<&str> = normalized.split('/').collect();
    if segments.contains(&"..") {
        return Err(FsError::InvalidPath("path contains '..' segment".into()));
    }
    if segments.len() > 1 && segments.iter().any(|segment| segment.is_empty()) {
        return Err(FsError::InvalidPath("path contains empty segment".into()));
    }
    Ok(())
}

#[must_use]
pub fn has_traversal(path: &str) -> bool {
    if cfg!(windows) {
        path.split(['/', '\\']).any(|part| part == "..")
    } else {
        path.split('/').any(|part| part == "..")
    }
}
#[allow(non_snake_case)]
pub fn ValidatePath(path: &str) -> Result<(), FsError> {
    validate_path(path)
}
#[allow(non_snake_case)]
#[must_use]
pub fn HasTraversal(path: &str) -> bool {
    has_traversal(path)
}
pub fn file_exists(path: impl AsRef<Path>) -> io::Result<bool> {
    match fs::symlink_metadata(path) {
        Ok(_) => Ok(true),
        Err(e) if e.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(e) => Err(e),
    }
}
#[allow(non_snake_case)]
pub fn FileExists(path: impl AsRef<Path>) -> io::Result<bool> {
    file_exists(path)
}

pub fn chmod(path: impl AsRef<Path>, mode: u32) -> io::Result<()> {
    set_mode(path, mode)
}
#[cfg(unix)]
pub fn set_mode(path: impl AsRef<Path>, mode: u32) -> io::Result<()> {
    let (parent, name) = secure_parent(path.as_ref()).map_err(io::Error::other)?;
    let file = openat(
        &parent,
        &name,
        OFlags::RDONLY | OFlags::NOFOLLOW,
        Mode::empty(),
    )
    .map_err(io::Error::from)?;
    fchmod(&file, Mode::from_raw_mode(mode as _)).map_err(io::Error::from)
}
#[cfg(windows)]
pub fn set_mode(path: impl AsRef<Path>, mode: u32) -> io::Result<()> {
    let (parent, name) = secure_parent_windows(path.as_ref()).map_err(io::Error::other)?;
    use cap_primitives::fs::OpenOptionsExt;
    const FILE_WRITE_ATTRIBUTES: u32 = 0x0100;
    let mut options = cap_primitives::fs::OpenOptions::new();
    options.access_mode(FILE_WRITE_ATTRIBUTES);
    options._cap_fs_ext_follow(cap_primitives::fs::FollowSymlinks::No);
    let file = cap_primitives::fs::open(&parent, &name, &options)?;
    let mut permissions = file.metadata()?.permissions();
    permissions.set_readonly(mode & 0o200 == 0);
    file.set_permissions(permissions)
}
#[cfg(unix)]
pub fn chmod_unix(path: impl AsRef<Path>, mode: u32) -> io::Result<()> {
    set_mode(path, mode)
}
#[cfg(windows)]
pub fn chmod_windows(path: impl AsRef<Path>, mode: u32) -> io::Result<()> {
    set_mode(path, mode)
}

/// Check every existing component, not just the leaf. Symlinks are rejected;
/// trusted roots (`/`, drive roots) are exempt from ownership/mode checks.
pub fn check_secure_dir(path: impl AsRef<Path>) -> Result<(), FsError> {
    let path = path.as_ref();
    #[cfg(unix)]
    {
        let (dir, _) = secure_parent_for_dir(path)?;
        let metadata = File::from(dir).metadata()?;
        if !metadata.is_dir() {
            return Err(FsError::NotDirectory(path.to_path_buf()));
        }
        if !is_secure_handle(&metadata, path) {
            return Err(FsError::InsecureDirectory(path.to_path_buf()));
        }
        Ok(())
    }
    #[cfg(windows)]
    {
        let (parent, name) = secure_parent_windows(path)?;
        let dir = cap_primitives::fs::open_dir_nofollow(&parent, &name).map_err(FsError::Io)?;
        let metadata = dir_metadata(&dir)?;
        if !metadata.is_dir() {
            return Err(FsError::NotDirectory(path.to_path_buf()));
        }
        Ok(())
    }
}

#[allow(non_snake_case)]
pub fn CheckSecureDir(path: impl AsRef<Path>) -> Result<(), FsError> {
    check_secure_dir(path)
}

pub fn safe_mkdir_all(path: impl AsRef<Path>, mode: u32) -> Result<(), FsError> {
    let path = path.as_ref();
    if path.as_os_str().is_empty() {
        return Err(FsError::InvalidPath("path is empty".into()));
    }
    #[cfg(unix)]
    {
        let absolute = trusted_absolute_path(path)?;
        let (root, parts) = directory_parts(&absolute)?;
        let mut dir = open_root(&root)?;
        let mut current = root.clone();
        for part in parts {
            let name = Path::new(&part);
            current.push(&part);
            match openat(
                &dir,
                name,
                OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
                Mode::empty(),
            ) {
                Ok(next) => {
                    let metadata = File::from(next.try_clone().map_err(|e| FsError::Io(e.into()))?)
                        .metadata()?;
                    if !metadata.is_dir() || !is_secure_handle(&metadata, &current) {
                        return Err(FsError::InsecureDirectory(absolute.clone()));
                    }
                    dir = next;
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    rustix::fs::mkdirat(&dir, name, Mode::from_raw_mode(mode as _))
                        .map_err(|error| FsError::Io(error.into()))?;
                    let next = openat(
                        &dir,
                        name,
                        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
                        Mode::empty(),
                    )
                    .map_err(|error| FsError::Io(error.into()))?;
                    let metadata = File::from(next.try_clone().map_err(|e| FsError::Io(e.into()))?)
                        .metadata()?;
                    if !metadata.is_dir() || !is_secure_handle(&metadata, &current) {
                        return Err(FsError::InsecureDirectory(absolute.clone()));
                    }
                    dir = next;
                }
                Err(error) => return Err(FsError::Io(error.into())),
            }
        }
        Ok(())
    }
    #[cfg(windows)]
    {
        let absolute = absolute_path(path)?;
        let (root, parts) = windows_directory_parts(&absolute)?;
        let mut dir = open_windows_root(&root)?;
        for part in parts {
            let child = match cap_primitives::fs::open_dir_nofollow(&dir, Path::new(&part)) {
                Ok(child) => child,
                Err(error) if error.kind() == io::ErrorKind::NotFound => {
                    cap_std::fs::Dir::from_std_file(dir.try_clone()?)
                        .create_dir(Path::new(&part))?;
                    cap_primitives::fs::open_dir_nofollow(&dir, Path::new(&part))?
                }
                Err(error) => return Err(FsError::Io(error)),
            };
            dir = child;
        }
        let _ = mode;
        Ok(())
    }
}

#[allow(non_snake_case)]
pub fn SafeMkdirAll(path: impl AsRef<Path>, mode: u32) -> Result<(), FsError> {
    safe_mkdir_all(path, mode)
}

pub fn safe_remove(path: impl AsRef<Path>) -> Result<(), FsError> {
    safe_remove_with_hook(path, || {})
}

/// Remove a regular file through a same-parent quarantine. The hook exists for
/// deterministic adversarial tests and runs after identity validation but
/// before the name is moved; production callers should use [`safe_remove`].
pub fn safe_remove_with_hook<F>(path: impl AsRef<Path>, before_rename: F) -> Result<(), FsError>
where
    F: FnOnce(),
{
    safe_remove_with_hooks(path, before_rename, close_file_checked)
}

#[doc(hidden)]
pub fn safe_remove_with_hooks<F, C>(
    path: impl AsRef<Path>,
    before_rename: F,
    close_file: C,
) -> Result<(), FsError>
where
    F: FnOnce(),
    C: FnOnce(File) -> io::Result<()>,
{
    let path = path.as_ref();
    #[cfg(unix)]
    {
        let (parent, name) = secure_parent(path)?;
        let fd = openat(
            &parent,
            &name,
            OFlags::RDONLY | OFlags::NOFOLLOW,
            Mode::empty(),
        )
        .map_err(|source| FsError::Atomic {
            path: path.to_path_buf(),
            source: source.into(),
        })?;
        let file = File::from(fd);
        let before = file.metadata()?;
        if !before.is_file() {
            return Err(FsError::NotRegular(path.to_path_buf()));
        }
        close_file(file)?;
        // Keep a second descriptor open across the rename. This preserves the
        // inode against immediate reuse while still surfacing the checked
        // close result from the descriptor required by the Go contract.
        let guard = File::from(
            openat(
                &parent,
                &name,
                OFlags::RDONLY | OFlags::NOFOLLOW,
                Mode::empty(),
            )
            .map_err(|error| FsError::Io(error.into()))?,
        );
        let guarded = guard.metadata()?;
        if !same_identity(&before, &guarded) || !guarded.is_file() {
            return Err(FsError::Atomic {
                path: path.to_path_buf(),
                source: io::Error::other("file identity changed before removal"),
            });
        }
        let quarantine = unique_sibling_name(&name);
        if statat(&parent, &quarantine, AtFlags::SYMLINK_NOFOLLOW).is_ok() {
            return Err(FsError::Atomic {
                path: path.to_path_buf(),
                source: io::Error::new(io::ErrorKind::AlreadyExists, "quarantine collision"),
            });
        }
        before_rename();
        renameat(&parent, &name, &parent, &quarantine)
            .map_err(|error| FsError::Io(error.into()))?;
        let moved = openat(
            &parent,
            &quarantine,
            OFlags::RDONLY | OFlags::NOFOLLOW,
            Mode::empty(),
        )
        .map_err(|error| FsError::Io(error.into()))?;
        let after = File::from(moved).metadata()?;
        if !same_identity(&guarded, &after) || !after.is_file() {
            return Err(FsError::Atomic {
                path: path.to_path_buf(),
                source: io::Error::other("file identity changed during removal"),
            });
        }
        unlinkat(&parent, &quarantine, AtFlags::empty())
            .map_err(|error| FsError::Io(error.into()))?;
        Ok(())
    }
    #[cfg(windows)]
    {
        let (parent, name) = secure_parent_windows(path)?;
        let file = open_windows_file(&parent, &name, true, false, false, false)?;
        let before = file.metadata()?;
        let before_identity = windows_file_identity(&file)?;
        if !before.is_file() {
            return Err(FsError::NotRegular(path.to_path_buf()));
        }
        close_file(file)?;
        let quarantine = unique_sibling_name(&name);
        let cap = cap_std::fs::Dir::from_std_file(parent.try_clone()?);
        before_rename();
        cap.rename(&name, &cap, &quarantine)?;
        let moved = open_windows_file(&parent, &quarantine, true, false, false, false)?;
        let after = moved.metadata()?;
        if windows_file_identity(&moved)? != before_identity || !after.is_file() {
            return Err(FsError::Atomic {
                path: path.to_path_buf(),
                source: io::Error::other("file identity changed during removal"),
            });
        }
        cap.remove_file(&quarantine)?;
        Ok(())
    }
}

#[cfg(unix)]
fn close_file_checked(file: File) -> io::Result<()> {
    use std::os::fd::IntoRawFd;
    nix::unistd::close(file.into_raw_fd()).map_err(io::Error::from)
}

#[cfg(windows)]
fn close_file_checked(file: File) -> io::Result<()> {
    drop(file);
    Ok(())
}

#[allow(non_snake_case)]
pub fn SafeRemove(path: impl AsRef<Path>) -> Result<(), FsError> {
    safe_remove(path)
}

pub fn write_file_atomic(path: impl AsRef<Path>, data: &[u8], mode: u32) -> Result<(), FsError> {
    let path = path.as_ref();
    #[cfg(unix)]
    {
        let (parent, name) = secure_parent(path)?;
        let temporary = temp_name(&name);
        let fd = openat(
            &parent,
            &temporary,
            OFlags::WRONLY | OFlags::CREATE | OFlags::EXCL | OFlags::NOFOLLOW,
            Mode::from_raw_mode(mode as _),
        )
        .map_err(|source| FsError::Atomic {
            path: path.to_path_buf(),
            source: source.into(),
        })?;
        fchmod(&fd, Mode::from_raw_mode(mode as _)).map_err(|source| FsError::Atomic {
            path: path.to_path_buf(),
            source: source.into(),
        })?;
        let mut file = File::from(fd);
        let result = (|| {
            file.write_all(data)
                .map_err(|error| FsError::Io(error.into()))?;
            file.sync_all().map_err(|error| FsError::Io(error.into()))?;
            drop(file);
            renameat(&parent, &temporary, &parent, &name).map_err(|source| FsError::Atomic {
                path: path.to_path_buf(),
                source: source.into(),
            })?;
            sync_directory(&parent)
        })();
        if result.is_err() {
            let _ = unlinkat(&parent, &temporary, AtFlags::empty());
        }
        result
    }
    #[cfg(windows)]
    {
        let (parent, name) = secure_parent_windows(path)?;
        let temporary = unique_sibling_name(&name);
        let file = open_windows_file(&parent, &temporary, false, true, false, true)?;
        let mut file = file;
        let result = (|| {
            use std::io::Write;
            let mut permissions = file.metadata()?.permissions();
            permissions.set_readonly(mode & 0o200 == 0);
            file.set_permissions(permissions)?;
            file.write_all(data)?;
            file.sync_all()?;
            drop(file);
            let cap = cap_std::fs::Dir::from_std_file(parent.try_clone()?);
            cap.rename(&temporary, &cap, &name)?;
            Ok::<(), io::Error>(())
        })();
        if result.is_err() {
            let cap = cap_std::fs::Dir::from_std_file(parent);
            let _ = cap.remove_file(&temporary);
        }
        result.map_err(|source| FsError::Atomic {
            path: path.to_path_buf(),
            source,
        })
    }
}

#[allow(non_snake_case)]
pub fn WriteFileAtomic(path: impl AsRef<Path>, data: &[u8], mode: u32) -> Result<(), FsError> {
    write_file_atomic(path, data, mode)
}

pub fn safe_write_file(path: impl AsRef<Path>, data: &[u8], mode: u32) -> Result<(), FsError> {
    let path = path.as_ref();
    #[cfg(windows)]
    let _ = mode;
    #[cfg(unix)]
    {
        let (parent, name) = secure_parent(path)?;
        let fd = openat(
            &parent,
            &name,
            OFlags::WRONLY | OFlags::CREATE | OFlags::TRUNC | OFlags::NOFOLLOW,
            Mode::from_raw_mode(mode as _),
        )
        .map_err(|source| FsError::Atomic {
            path: path.to_path_buf(),
            source: source.into(),
        })?;
        let mut file = File::from(fd);
        if !file.metadata()?.is_file() {
            return Err(FsError::NotRegular(path.to_path_buf()));
        }
        file.write_all(data)
            .map_err(|error| FsError::Io(error.into()))
    }
    #[cfg(windows)]
    {
        let (parent, name) = secure_parent_windows(path)?;
        if let Ok(metadata) =
            cap_primitives::fs::stat(&parent, &name, cap_primitives::fs::FollowSymlinks::No)
            && metadata.is_dir()
        {
            return Err(FsError::NotRegular(path.to_path_buf()));
        }
        let mut file = open_windows_file(&parent, &name, false, true, true, false)?;
        if !file.metadata()?.is_file() {
            return Err(FsError::NotRegular(path.to_path_buf()));
        }
        use std::io::Write;
        file.write_all(data).map_err(FsError::Io)
    }
}

#[allow(non_snake_case)]
pub fn SafeWriteFile(path: impl AsRef<Path>, data: &[u8], mode: u32) -> Result<(), FsError> {
    safe_write_file(path, data, mode)
}

#[cfg(unix)]
fn secure_metadata(metadata: &fs::Metadata) -> bool {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let uid = rustix::process::geteuid().as_raw();
    (metadata.uid() == uid || metadata.uid() == 0) && metadata.permissions().mode() & 0o022 == 0
}
#[cfg(unix)]
fn is_secure_handle(metadata: &fs::Metadata, path: &Path) -> bool {
    is_trusted_root(path)
        || secure_metadata(metadata)
        || is_trusted_system_directory(metadata, path)
}
#[cfg(unix)]
fn is_trusted_system_directory(metadata: &fs::Metadata, path: &Path) -> bool {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};
    let root_owned = metadata.uid() == 0;
    let mode = metadata.permissions().mode() & 0o7777;
    if matches!(path, p if p == Path::new("/tmp") || p == Path::new("/var/tmp")) {
        return root_owned && mode & 0o1000 != 0 && mode & 0o022 == 0o022;
    }
    #[cfg(target_os = "macos")]
    {
        if path == Path::new("/private/tmp") {
            return root_owned && mode & 0o1000 != 0 && mode & 0o022 == 0o022;
        }
        if matches!(path, p if p == Path::new("/private")
            || p == Path::new("/private/var")
            || p == Path::new("/private/etc"))
        {
            return root_owned && mode & 0o022 == 0;
        }
    }
    let _ = (metadata, path);
    false
}
#[cfg(unix)]
#[cfg(any())]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct FileIdentity {
    dev: u64,
    ino: u64,
}
#[cfg(windows)]
type FileIdentity = same_file::Handle;
#[cfg(unix)]
#[cfg(any())]
fn file_identity(metadata: &fs::Metadata) -> FileIdentity {
    use std::os::unix::fs::MetadataExt;
    FileIdentity {
        dev: metadata.dev(),
        ino: metadata.ino(),
    }
}

#[cfg(unix)]
#[cfg(any())]
fn stat_identity(stat: &rustix::fs::Stat) -> FileIdentity {
    FileIdentity {
        dev: stat.st_dev as u64,
        ino: stat.st_ino,
    }
}
#[cfg(unix)]
fn same_identity(a: &fs::Metadata, b: &fs::Metadata) -> bool {
    use std::os::unix::fs::MetadataExt;
    a.dev() == b.dev() && a.ino() == b.ino()
}
#[cfg(unix)]
#[cfg(any())]
fn verify_directory_identity(
    parent: &std::os::fd::OwnedFd,
    name: &OsStr,
    expected: FileIdentity,
    display_path: &Path,
) -> Result<(), FsError> {
    let stat = statat(parent, name, AtFlags::SYMLINK_NOFOLLOW)
        .map_err(|error| FsError::Io(error.into()))?;
    if !FileType::from_raw_mode(stat.st_mode).is_dir() || stat_identity(&stat) != expected {
        return Err(FsError::InsecureDirectory(display_path.to_path_buf()));
    }
    Ok(())
}
#[cfg(windows)]
fn windows_file_identity(file: &File) -> io::Result<FileIdentity> {
    same_file::Handle::from_file(file.try_clone()?)
}
#[cfg(windows)]
#[cfg(any())]
fn verify_directory_identity_windows(
    parent: &File,
    name: &Path,
    expected: &FileIdentity,
    display_path: &Path,
) -> Result<(), FsError> {
    let file = open_windows_file(parent, name, true, false, false, false)?;
    if !file.metadata()?.is_dir() || windows_file_identity(&file)? != *expected {
        return Err(FsError::InsecureDirectory(display_path.to_path_buf()));
    }
    Ok(())
}
#[cfg(unix)]
fn is_trusted_root(path: &Path) -> bool {
    path == Path::new("/") || path.parent().is_none() || path.components().count() == 1
}
#[cfg(unix)]
fn trusted_absolute_path(path: &Path) -> Result<PathBuf, FsError> {
    let absolute = absolute_path(path)?;
    #[cfg(target_os = "macos")]
    {
        // macOS ships these root-owned aliases. Rewrite only these exact,
        // documented aliases; never canonicalize attacker-controlled input.
        for alias in ["/var", "/tmp", "/etc"] {
            if absolute == Path::new(alias) || absolute.starts_with(format!("{alias}/")) {
                return Ok(PathBuf::from("/private").join(absolute.strip_prefix("/").unwrap()));
            }
        }
    }
    Ok(absolute)
}
#[cfg(unix)]
fn secure_parent_for_dir(path: &Path) -> Result<(std::os::fd::OwnedFd, PathBuf), FsError> {
    let absolute = trusted_absolute_path(path)?;
    let (root, parts) = directory_parts(&absolute)?;
    let mut dir = open_root(&root)?;
    let mut current = root.clone();
    for part in parts {
        let next = openat(
            &dir,
            Path::new(&part),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
            Mode::empty(),
        )
        .map_err(|error| FsError::Io(error.into()))?;
        let metadata =
            File::from(next.try_clone().map_err(|e| FsError::Io(e.into()))?).metadata()?;
        current.push(&part);
        if !metadata.is_dir() || !is_secure_handle(&metadata, &current) {
            return Err(FsError::InsecureDirectory(absolute));
        }
        dir = next;
    }
    Ok((dir, absolute))
}
#[cfg(unix)]
#[cfg(any())]
fn secure_stat(stat: &rustix::fs::Stat) -> bool {
    let uid = rustix::process::geteuid().as_raw();
    (stat.st_uid == uid || stat.st_uid == 0) && stat.st_mode & 0o022 == 0
}
fn absolute_path(path: &Path) -> Result<PathBuf, FsError> {
    if path.is_absolute() {
        Ok(path.to_path_buf())
    } else {
        Ok(std::env::current_dir()?.join(path))
    }
}
#[cfg(windows)]
fn windows_directory_parts(path: &Path) -> Result<(PathBuf, Vec<PathBuf>), FsError> {
    let mut root = PathBuf::new();
    let mut parts = Vec::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => root.push(prefix.as_os_str()),
            Component::RootDir => root.push("\\"),
            Component::Normal(name) => parts.push(name.to_owned().into()),
            Component::CurDir => {}
            Component::ParentDir => {
                return Err(FsError::InvalidPath(
                    "parent components are forbidden for secure operations".into(),
                ));
            }
        }
    }
    if root.as_os_str().is_empty() {
        return Err(FsError::InvalidPath("path has no Windows root".into()));
    }
    Ok((root, parts))
}
#[cfg(windows)]
fn open_windows_root(root: &Path) -> Result<std::fs::File, FsError> {
    cap_primitives::fs::open_ambient_dir(root, cap_std::ambient_authority()).map_err(FsError::Io)
}
#[cfg(windows)]
fn dir_metadata(dir: &std::fs::File) -> Result<fs::Metadata, FsError> {
    dir.metadata().map_err(FsError::Io)
}
#[cfg(windows)]
fn secure_parent_windows(path: &Path) -> Result<(std::fs::File, PathBuf), FsError> {
    let absolute = absolute_path(path)?;
    let parent = absolute
        .parent()
        .ok_or_else(|| FsError::InvalidPath("missing parent".into()))?;
    let name = absolute
        .file_name()
        .ok_or_else(|| FsError::InvalidPath("missing filename".into()))?
        .to_owned();
    let (root, parts) = windows_directory_parts(parent)?;
    let mut dir = open_windows_root(&root)?;
    for part in parts {
        dir = cap_primitives::fs::open_dir_nofollow(&dir, &part).map_err(FsError::Io)?;
    }
    Ok((dir, PathBuf::from(name)))
}
#[cfg(windows)]
fn open_windows_file(
    parent: &std::fs::File,
    name: &Path,
    read: bool,
    create: bool,
    truncate: bool,
    create_new: bool,
) -> Result<std::fs::File, FsError> {
    let mut options = cap_primitives::fs::OpenOptions::new();
    options
        .read(read)
        .write(!read)
        .create(create)
        .truncate(truncate)
        .create_new(create_new);
    options._cap_fs_ext_follow(cap_primitives::fs::FollowSymlinks::No);
    cap_primitives::fs::open(parent, name, &options).map_err(FsError::Io)
}
fn unique_sibling_name(name: &Path) -> PathBuf {
    temp_name(name)
}
#[cfg(unix)]
fn directory_parts(path: &Path) -> Result<(PathBuf, Vec<String>), FsError> {
    let mut parts = Vec::new();
    let mut root = PathBuf::new();
    for component in path.components() {
        match component {
            Component::RootDir => root.push("/"),
            Component::Normal(name) => parts.push(name.to_string_lossy().into_owned()),
            Component::CurDir => {}
            Component::ParentDir => {
                return Err(FsError::InvalidPath(
                    "parent components are forbidden for secure operations".into(),
                ));
            }
            Component::Prefix(_) => {
                return Err(FsError::InvalidPath("path prefix is unsupported".into()));
            }
        }
    }
    if root.as_os_str().is_empty() {
        root.push(".");
    }
    Ok((root, parts))
}
#[cfg(unix)]
fn open_root(root: &Path) -> Result<std::os::fd::OwnedFd, FsError> {
    open(
        root,
        OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
        Mode::empty(),
    )
    .map_err(|error| FsError::Io(error.into()))
}
#[cfg(unix)]
fn secure_parent(path: &Path) -> Result<(std::os::fd::OwnedFd, PathBuf), FsError> {
    let absolute = trusted_absolute_path(path)?;
    let parent = absolute
        .parent()
        .ok_or_else(|| FsError::InvalidPath("missing parent".into()))?;
    let name = absolute
        .file_name()
        .ok_or_else(|| FsError::InvalidPath("missing filename".into()))?;
    let (root, parts) = directory_parts(parent)?;
    let mut dir = open_root(&root)?;
    let mut current = root.clone();
    for part in parts {
        let next = openat(
            &dir,
            Path::new(&part),
            OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
            Mode::empty(),
        )
        .map_err(|error| FsError::Io(error.into()))?;
        let metadata =
            File::from(next.try_clone().map_err(|e| FsError::Io(e.into()))?).metadata()?;
        current.push(&part);
        if !metadata.is_dir() || !is_secure_handle(&metadata, &current) {
            return Err(FsError::InsecureDirectory(parent.to_path_buf()));
        }
        dir = next;
    }
    Ok((dir, PathBuf::from(name)))
}
fn temp_name(name: &Path) -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let n = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
    PathBuf::from(format!(".{}.tmp-{stamp:x}-{n:x}", name.to_string_lossy()))
}
#[cfg(unix)]
fn sync_directory(dir: &std::os::fd::OwnedFd) -> Result<(), FsError> {
    File::from(dir.try_clone().map_err(|error| FsError::Io(error.into()))?)
        .sync_all()
        .map_err(|error| FsError::Io(error.into()))
}

pub struct FileLock {
    file: File,
    path: PathBuf,
}
impl std::fmt::Debug for FileLock {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("FileLock")
            .field("path", &self.path)
            .finish()
    }
}
impl FileLock {
    pub fn try_lock(path: impl AsRef<Path>) -> Result<Self, FsError> {
        let path = path.as_ref();
        #[cfg(unix)]
        {
            let (parent, name) = secure_parent(path)?;
            let fd = openat(
                &parent,
                &name,
                OFlags::CREATE | OFlags::RDWR | OFlags::NOFOLLOW,
                Mode::from_raw_mode(0o600),
            )
            .map_err(|error| FsError::Io(error.into()))?;
            let file = File::from(fd);
            file.try_lock_exclusive()
                .map_err(|error| FsError::Io(error.into()))?;
            return Ok(Self {
                file,
                path: path.to_path_buf(),
            });
        }
        #[cfg(windows)]
        {
            let (parent, name) = secure_parent_windows(path)?;
            let file = open_windows_file(&parent, &name, false, true, false, false)?;
            file.try_lock_exclusive().map_err(FsError::Io)?;
            return Ok(Self {
                file,
                path: path.to_path_buf(),
            });
        }
    }
    pub fn lock_nonblocking(path: impl AsRef<Path>) -> Result<Self, FsError> {
        Self::try_lock(path)
    }
}
impl Drop for FileLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
    }
}

// A directory-swap API is deliberately not exported in this slice. Safe Rust
// cannot provide race-free recursive cleanup on every supported platform;
// shipping a path-based approximation would violate the fail-closed contract.
#[cfg(any())]
pub struct DirSwap {
    target: PathBuf,
    staging: PathBuf,
    backup: PathBuf,
    staging_identity: FileIdentity,
    target_identity: Option<FileIdentity>,
    committed: bool,
}
#[cfg(any())]
impl std::fmt::Debug for DirSwap {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("DirSwap")
            .field("target", &self.target)
            .field("staging", &self.staging)
            .field("backup", &self.backup)
            .field("committed", &self.committed)
            .finish()
    }
}
#[cfg(any())]
impl DirSwap {
    pub fn new(target: impl AsRef<Path>, staging: impl AsRef<Path>) -> Result<Self, FsError> {
        let target = target.as_ref().to_path_buf();
        let staging = staging.as_ref().to_path_buf();
        let target_abs = absolute_path(&target)?;
        let staging_abs = absolute_path(&staging)?;
        let parent = target_abs
            .parent()
            .ok_or_else(|| FsError::InvalidPath("target has no parent".into()))?
            .to_path_buf();
        if staging_abs.parent() != Some(parent.as_path()) {
            return Err(FsError::UnsupportedSecurity(
                "staging and target must share a parent capability".into(),
            ));
        }
        let (staging_identity, target_identity);
        #[cfg(unix)]
        {
            let (p, sname) = secure_parent(&staging_abs)?;
            let sm_file = File::from(
                openat(
                    &p,
                    &sname,
                    OFlags::RDONLY | OFlags::DIRECTORY | OFlags::NOFOLLOW,
                    Mode::empty(),
                )
                .map_err(|e| FsError::Io(e.into()))?,
            );
            let sm = sm_file.metadata().map_err(FsError::Io)?;
            if !sm.is_dir() {
                return Err(FsError::NotDirectory(staging));
            }
            staging_identity = file_identity(&sm);
            let tname = target_abs
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("target has no filename".into()))?;
            target_identity = match statat(&p, tname, AtFlags::SYMLINK_NOFOLLOW) {
                Ok(stat) if FileType::from_raw_mode(stat.st_mode).is_dir() => {
                    Some(stat_identity(&stat))
                }
                Ok(_) => return Err(FsError::NotDirectory(target)),
                Err(error) if error.kind() == io::ErrorKind::NotFound => None,
                Err(error) => return Err(FsError::Io(error.into())),
            };
            let stamp = TEMP_COUNTER.fetch_add(1, Ordering::Relaxed);
            let backup = parent.join(format!(
                ".{}.symaira-backup-{stamp:x}",
                tname.to_string_lossy()
            ));
            return Ok(Self {
                target: target_abs,
                staging: staging_abs,
                backup,
                staging_identity,
                target_identity,
                committed: false,
            });
        }
        #[cfg(windows)]
        {
            let (p, sname) = secure_parent_windows(&staging_abs)?;
            let sm = open_windows_file(&p, &sname, true, false, false, false)?;
            let metadata = sm.metadata()?;
            if !metadata.is_dir() {
                return Err(FsError::NotDirectory(staging));
            }
            staging_identity = windows_file_identity(&sm)?;
            let tname = target_abs
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("target has no filename".into()))?;
            target_identity =
                match open_windows_file(&p, Path::new(tname), true, false, false, false) {
                    Ok(file) => {
                        let m = file.metadata()?;
                        if !m.is_dir() {
                            return Err(FsError::NotDirectory(target));
                        }
                        Some(windows_file_identity(&file)?)
                    }
                    Err(FsError::Io(e)) if e.kind() == io::ErrorKind::NotFound => None,
                    Err(error) => return Err(error),
                };
            let backup = parent.join(format!(
                ".{}.symaira-backup-{}",
                tname.to_string_lossy(),
                std::process::id()
            ));
            return Ok(Self {
                target: target_abs,
                staging: staging_abs,
                backup,
                staging_identity,
                target_identity,
                committed: false,
            });
        }
        #[cfg(not(any(unix, windows)))]
        {
            let _ = (target, staging, parent);
            Err(FsError::UnsupportedSecurity(
                "directory swap requires a reparse-safe capability".into(),
            ))
        }
    }
    pub fn commit(&mut self) -> Result<(), FsError> {
        self.commit_with_hook(|| {})
    }

    fn commit_with_hook<F>(&mut self, before_rename: F) -> Result<(), FsError>
    where
        F: FnOnce(),
    {
        #[cfg(unix)]
        {
            let (parent, target_name) = secure_parent(&self.target)?;
            let (_, staging_name) = secure_parent(&self.staging)?;
            let backup_name = self
                .backup
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("backup has no filename".into()))?;
            let target_stat = rustix::fs::statat(&parent, &target_name, AtFlags::SYMLINK_NOFOLLOW);
            let (had, target_id_now) = match target_stat {
                Ok(stat) => {
                    let ty = FileType::from_raw_mode(stat.st_mode);
                    if ty.is_symlink() || !ty.is_dir() {
                        return Err(FsError::InsecureDirectory(self.target.clone()));
                    }
                    (true, Some(stat_identity(&stat)))
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => (false, None),
                Err(error) => return Err(FsError::Io(error.into())),
            };
            let staging_stat =
                rustix::fs::statat(&parent, &staging_name, AtFlags::SYMLINK_NOFOLLOW)
                    .map_err(|error| FsError::Io(error.into()))?;
            let staging_type = FileType::from_raw_mode(staging_stat.st_mode);
            if staging_type.is_symlink()
                || !staging_type.is_dir()
                || stat_identity(&staging_stat) != self.staging_identity
            {
                return Err(FsError::InsecureDirectory(self.staging.clone()));
            }
            if (had && self.target_identity != target_id_now)
                || (!had && self.target_identity.is_some())
            {
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::other("target identity changed before swap"),
                });
            }
            if statat(&parent, backup_name, AtFlags::SYMLINK_NOFOLLOW).is_ok() {
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::new(io::ErrorKind::AlreadyExists, "backup collision"),
                });
            }
            before_rename();
            if had {
                renameat(&parent, &target_name, &parent, backup_name)
                    .map_err(|error| FsError::Io(error.into()))?;
            }
            if let Err(source) = renameat(&parent, &staging_name, &parent, &target_name) {
                if had {
                    let expected = self.target_identity.ok_or_else(|| FsError::Atomic {
                        path: self.target.clone(),
                        source: io::Error::other("missing target identity for rollback"),
                    })?;
                    verify_directory_identity(&parent, backup_name, expected, &self.backup)?;
                    renameat(&parent, backup_name, &parent, &target_name)
                        .map_err(|error| FsError::Io(error.into()))?;
                }
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: source.into(),
                });
            }
            let installed = statat(&parent, &target_name, AtFlags::SYMLINK_NOFOLLOW)
                .map_err(|error| FsError::Io(error.into()))?;
            if !FileType::from_raw_mode(installed.st_mode).is_dir()
                || stat_identity(&installed) != self.staging_identity
            {
                let quarantine = unique_sibling_name(&target_name);
                let _ = renameat(&parent, &target_name, &parent, &quarantine);
                if had {
                    let expected = self.target_identity.ok_or_else(|| FsError::Atomic {
                        path: self.target.clone(),
                        source: io::Error::other("missing target identity for rollback"),
                    })?;
                    verify_directory_identity(&parent, backup_name, expected, &self.backup)?;
                    renameat(&parent, backup_name, &parent, &target_name)
                        .map_err(|error| FsError::Io(error.into()))?;
                }
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::other("staging identity changed during swap"),
                });
            }
            if had {
                let expected = self.target_identity.ok_or_else(|| FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::other("missing target identity for cleanup"),
                })?;
                verify_directory_identity(&parent, backup_name, expected, &self.backup)?;
                let backup = cap_std::fs::Dir::from_std_file(File::from(
                    parent
                        .try_clone()
                        .map_err(|error| FsError::Io(error.into()))?,
                ));
                backup
                    .remove_dir_all(backup_name)
                    .map_err(|error| FsError::Io(error.into()))?;
            }
            sync_directory(&parent)?;
            self.committed = true;
            Ok(())
        }
        #[cfg(windows)]
        {
            let (parent, target_name) = secure_parent_windows(&self.target)?;
            let (_, staging_name) = secure_parent_windows(&self.staging)?;
            let backup_name = self
                .backup
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("backup has no filename".into()))?;
            let target_now =
                match open_windows_file(&parent, &target_name, true, false, false, false) {
                    Ok(file) => {
                        let m = file.metadata()?;
                        if !m.is_dir() {
                            return Err(FsError::InsecureDirectory(self.target.clone()));
                        }
                        Some(windows_file_identity(&file)?)
                    }
                    Err(FsError::Io(e)) if e.kind() == io::ErrorKind::NotFound => None,
                    Err(error) => return Err(error),
                };
            if target_now != self.target_identity {
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::other("target identity changed before swap"),
                });
            }
            let stage = open_windows_file(&parent, &staging_name, true, false, false, false)?;
            let sm = stage.metadata()?;
            if !sm.is_dir() || windows_file_identity(&stage)? != self.staging_identity {
                return Err(FsError::InsecureDirectory(self.staging.clone()));
            }
            if open_windows_file(&parent, Path::new(backup_name), true, false, false, false).is_ok()
            {
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::new(io::ErrorKind::AlreadyExists, "backup collision"),
                });
            }
            let cap = cap_std::fs::Dir::from_std_file(parent.try_clone()?);
            before_rename();
            if self.target_identity.is_some() {
                cap.rename(&target_name, &cap, Path::new(backup_name))?;
            }
            if let Err(error) = cap.rename(&staging_name, &cap, &target_name) {
                if let Some(expected) = self.target_identity.as_ref() {
                    verify_directory_identity_windows(
                        &parent,
                        Path::new(backup_name),
                        expected,
                        &self.backup,
                    )?;
                    cap.rename(Path::new(backup_name), &cap, &target_name)?;
                }
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: error,
                });
            }
            let installed = open_windows_file(&parent, &target_name, true, false, false, false)?;
            if !installed.metadata()?.is_dir()
                || windows_file_identity(&installed)? != self.staging_identity
            {
                drop(installed);
                let quarantine = unique_sibling_name(&target_name);
                let _ = cap.rename(&target_name, &cap, &quarantine);
                if let Some(expected) = self.target_identity.as_ref() {
                    verify_directory_identity_windows(
                        &parent,
                        Path::new(backup_name),
                        expected,
                        &self.backup,
                    )?;
                    cap.rename(Path::new(backup_name), &cap, &target_name)?;
                }
                return Err(FsError::Atomic {
                    path: self.target.clone(),
                    source: io::Error::other("staging identity changed during swap"),
                });
            }
            if let Some(expected) = self.target_identity.as_ref() {
                verify_directory_identity_windows(
                    &parent,
                    Path::new(backup_name),
                    expected,
                    &self.backup,
                )?;
                cap.remove_dir_all(Path::new(backup_name))?;
            }
            self.committed = true;
            Ok(())
        }
        #[cfg(not(any(unix, windows)))]
        {
            Err(FsError::UnsupportedSecurity(
                "directory swap requires a reparse-safe capability".into(),
            ))
        }
    }
    pub fn rollback(&mut self) -> Result<(), FsError> {
        #[cfg(unix)]
        {
            let (parent, target_name) = secure_parent(&self.target)?;
            let staging_name = self
                .staging
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("staging has no filename".into()))?;
            let backup_name = self
                .backup
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("backup has no filename".into()))?;
            let cap = cap_std::fs::Dir::from_std_file(File::from(
                parent
                    .try_clone()
                    .map_err(|error| FsError::Io(error.into()))?,
            ));
            if statat(&parent, staging_name, AtFlags::SYMLINK_NOFOLLOW).is_ok() {
                verify_directory_identity(
                    &parent,
                    staging_name,
                    self.staging_identity,
                    &self.staging,
                )?;
                cap.remove_dir_all(staging_name)
                    .map_err(|error| FsError::Io(error.into()))?;
            }
            if statat(&parent, backup_name, AtFlags::SYMLINK_NOFOLLOW).is_ok() {
                if statat(&parent, &target_name, AtFlags::SYMLINK_NOFOLLOW).is_ok() {
                    return Err(FsError::Atomic {
                        path: self.target.clone(),
                        source: io::Error::other("target exists while backup awaits rollback"),
                    });
                }
                let expected = self.target_identity.ok_or_else(|| FsError::Atomic {
                    path: self.backup.clone(),
                    source: io::Error::other("unexpected backup without target identity"),
                })?;
                verify_directory_identity(&parent, backup_name, expected, &self.backup)?;
                renameat(&parent, backup_name, &parent, &target_name)
                    .map_err(|error| FsError::Io(error.into()))?;
            }
            Ok(())
        }
        #[cfg(windows)]
        {
            let (parent, target_name) = secure_parent_windows(&self.target)?;
            let staging_name = self
                .staging
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("staging has no filename".into()))?;
            let backup_name = self
                .backup
                .file_name()
                .ok_or_else(|| FsError::InvalidPath("backup has no filename".into()))?;
            let cap = cap_std::fs::Dir::from_std_file(parent.try_clone()?);
            if open_windows_file(&parent, Path::new(staging_name), true, false, false, false)
                .is_ok()
            {
                verify_directory_identity_windows(
                    &parent,
                    Path::new(staging_name),
                    &self.staging_identity,
                    &self.staging,
                )?;
                cap.remove_dir_all(Path::new(staging_name))?;
            }
            if open_windows_file(&parent, Path::new(backup_name), true, false, false, false).is_ok()
            {
                if open_windows_file(&parent, &target_name, true, false, false, false).is_ok() {
                    return Err(FsError::Atomic {
                        path: self.target.clone(),
                        source: io::Error::other("target exists while backup awaits rollback"),
                    });
                }
                let expected = self
                    .target_identity
                    .as_ref()
                    .ok_or_else(|| FsError::Atomic {
                        path: self.backup.clone(),
                        source: io::Error::other("unexpected backup without target identity"),
                    })?;
                verify_directory_identity_windows(
                    &parent,
                    Path::new(backup_name),
                    expected,
                    &self.backup,
                )?;
                cap.rename(Path::new(backup_name), &cap, &target_name)?;
            }
            Ok(())
        }
        #[cfg(not(any(unix, windows)))]
        {
            Err(FsError::UnsupportedSecurity(
                "directory recovery requires a reparse-safe capability".into(),
            ))
        }
    }
    pub fn recover(target: impl AsRef<Path>) -> Result<bool, FsError> {
        Self::recover_with_hook(target, || {})
    }

    fn recover_with_hook<F>(target: impl AsRef<Path>, before_rename: F) -> Result<bool, FsError>
    where
        F: FnOnce(),
    {
        let target = target.as_ref();
        #[cfg(unix)]
        {
            let (parent, name) = secure_parent(target)?;
            match statat(&parent, &name, AtFlags::SYMLINK_NOFOLLOW) {
                Ok(stat) => {
                    let ty = FileType::from_raw_mode(stat.st_mode);
                    if ty.is_symlink() {
                        return Err(FsError::InsecureDirectory(target.to_path_buf()));
                    }
                    return Ok(false);
                }
                Err(error) if error.kind() == io::ErrorKind::NotFound => {}
                Err(error) => return Err(FsError::Io(error.into())),
            }
            let prefix = format!(".{}.symaira-backup-", name.to_string_lossy());
            let mut found = None;
            for entry in cap_std::fs::Dir::from_std_file(File::from(
                parent
                    .try_clone()
                    .map_err(|error| FsError::Io(error.into()))?,
            ))
            .entries()
            .map_err(|error| FsError::Io(error.into()))?
            {
                let entry = entry.map_err(|error| FsError::Io(error.into()))?;
                let n = entry.file_name();
                if !n.to_string_lossy().starts_with(&prefix) {
                    continue;
                }
                let candidate_name = n.to_string_lossy();
                let suffix = candidate_name.strip_prefix(&prefix).unwrap_or_default();
                if suffix.is_empty() || !suffix.bytes().all(|byte| byte.is_ascii_hexdigit()) {
                    continue;
                }
                let stat = statat(&parent, &n, AtFlags::SYMLINK_NOFOLLOW)
                    .map_err(|error| FsError::Io(error.into()))?;
                if FileType::from_raw_mode(stat.st_mode).is_symlink()
                    || !FileType::from_raw_mode(stat.st_mode).is_dir()
                    || !secure_stat(&stat)
                {
                    return Err(FsError::InsecureDirectory(target.to_path_buf()));
                }
                if found.is_some() {
                    return Err(FsError::InsecureDirectory(target.to_path_buf()));
                }
                found = Some((n, stat_identity(&stat)));
            }
            if let Some((candidate, expected_identity)) = found {
                let cap = cap_std::fs::Dir::from_std_file(File::from(
                    parent
                        .try_clone()
                        .map_err(|error| FsError::Io(error.into()))?,
                ));
                before_rename();
                cap.rename(&candidate, &cap, &name)
                    .map_err(|error| FsError::Io(error.into()))?;
                let installed = statat(&parent, &name, AtFlags::SYMLINK_NOFOLLOW)
                    .map_err(|error| FsError::Io(error.into()))?;
                if !FileType::from_raw_mode(installed.st_mode).is_dir()
                    || stat_identity(&installed) != expected_identity
                {
                    let quarantine = unique_sibling_name(&name);
                    let _ = renameat(&parent, &name, &parent, &quarantine);
                    return Err(FsError::Atomic {
                        path: target.to_path_buf(),
                        source: io::Error::other("backup identity changed during recovery"),
                    });
                }
                return Ok(true);
            }
            Ok(false)
        }
        #[cfg(windows)]
        {
            let (parent, name) = secure_parent_windows(target)?;
            if open_windows_file(&parent, &name, true, false, false, false).is_ok() {
                return Ok(false);
            }
            let prefix = format!(".{}.symaira-backup-", name.to_string_lossy());
            let cap = cap_std::fs::Dir::from_std_file(parent.try_clone()?);
            let mut candidate: Option<(PathBuf, FileIdentity)> = None;
            for entry in cap.entries()? {
                let entry = entry?;
                let candidate_name = entry.file_name();
                let text = candidate_name.to_string_lossy();
                let Some(suffix) = text.strip_prefix(&prefix) else {
                    continue;
                };
                if suffix.is_empty() || !suffix.bytes().all(|byte| byte.is_ascii_digit()) {
                    continue;
                }
                let candidate_file = open_windows_file(
                    &parent,
                    Path::new(&candidate_name),
                    true,
                    false,
                    false,
                    false,
                )?;
                let metadata = candidate_file.metadata()?;
                if !metadata.is_dir() {
                    return Err(FsError::InsecureDirectory(target.to_path_buf()));
                }
                let identity = windows_file_identity(&candidate_file)?;
                if candidate
                    .replace((candidate_name.into(), identity))
                    .is_some()
                {
                    return Err(FsError::InsecureDirectory(target.to_path_buf()));
                }
            }
            if let Some((candidate, expected_identity)) = candidate {
                if open_windows_file(&parent, &name, true, false, false, false).is_ok() {
                    return Err(FsError::Atomic {
                        path: target.to_path_buf(),
                        source: io::Error::other("target appeared during recovery"),
                    });
                }
                before_rename();
                cap.rename(&candidate, &cap, &name)?;
                let installed = open_windows_file(&parent, &name, true, false, false, false)?;
                if !installed.metadata()?.is_dir()
                    || windows_file_identity(&installed)? != expected_identity
                {
                    drop(installed);
                    let quarantine = unique_sibling_name(&name);
                    let _ = cap.rename(&name, &cap, &quarantine);
                    return Err(FsError::Atomic {
                        path: target.to_path_buf(),
                        source: io::Error::other("backup identity changed during recovery"),
                    });
                }
                return Ok(true);
            }
            Ok(false)
        }
        #[cfg(not(any(unix, windows)))]
        {
            let _ = target;
            Err(FsError::UnsupportedSecurity(
                "directory recovery requires a reparse-safe capability".into(),
            ))
        }
    }
}
#[cfg(any())]
impl Drop for DirSwap {
    fn drop(&mut self) {
        if !self.committed {
            let _ = self.rollback();
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;
    #[test]
    fn path_guard_is_target_native() {
        assert!(validate_path("a\\..\\b").is_err());
        assert!(validate_path(r"C:\tmp\x").is_ok());
    }
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn atomic_write_replaces() {
        let d = tempdir().unwrap();
        let p = d.path().join("v");
        write_file_atomic(&p, b"one", 0o600).unwrap();
        write_file_atomic(&p, b"two", 0o600).unwrap();
        assert_eq!(fs::read(p).unwrap(), b"two");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mode_path = d.path().join("mode");
            write_file_atomic(&mode_path, b"mode", 0o666).unwrap();
            assert_eq!(
                fs::metadata(mode_path).unwrap().permissions().mode() & 0o777,
                0o666
            );
        }
    }

    #[test]
    fn temporary_names_are_unique_per_call() {
        let name = Path::new("value");
        let first = unique_sibling_name(name);
        let second = unique_sibling_name(name);
        assert_ne!(first, second);
    }
    #[cfg(unix)]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn secure_mutations_reject_symlink_and_insecure_recovery_inputs() {
        use std::os::unix::fs::{PermissionsExt, symlink};
        let root = tempdir().unwrap();
        let outside = root.path().join("outside");
        fs::write(&outside, b"outside").unwrap();
        let link = root.path().join("link");
        symlink(&outside, &link).unwrap();
        let outside_mode = fs::metadata(&outside).unwrap().permissions().mode();
        assert!(safe_remove(&link).is_err());
        assert!(chmod(&link, 0o600).is_err());
        assert!(FileLock::try_lock(&link).is_err());
        assert_eq!(fs::read(&outside).unwrap(), b"outside");
        assert_eq!(
            fs::metadata(&outside).unwrap().permissions().mode(),
            outside_mode
        );

        let nested = root.path().join("nested/child");
        fs::create_dir_all(&nested).unwrap();
        fs::set_permissions(
            root.path().join("nested"),
            fs::Permissions::from_mode(0o777),
        )
        .unwrap();
        assert!(check_secure_dir(&nested).is_err());
    }

    #[cfg(unix)]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn safe_remove_quarantine_fails_closed_on_leaf_swap() {
        let root = tempdir().unwrap();
        let victim = root.path().join("victim");
        fs::write(&victim, b"original").unwrap();
        let result = safe_remove_with_hook(&victim, || {
            fs::remove_file(&victim).unwrap();
            fs::write(&victim, b"attacker-selected").unwrap();
        });
        assert!(result.is_err());
        assert!(!file_exists(&victim).unwrap());
        let quarantined: Vec<_> = fs::read_dir(root.path())
            .unwrap()
            .flatten()
            .filter(|entry| {
                entry
                    .file_name()
                    .to_string_lossy()
                    .starts_with(".victim.tmp-")
            })
            .collect();
        assert_eq!(quarantined.len(), 1);
        assert_eq!(
            fs::read(quarantined[0].path()).unwrap(),
            b"attacker-selected"
        );

        let close_fault = root.path().join("close-fault");
        fs::write(&close_fault, b"preserved").unwrap();
        let result = safe_remove_with_hooks(
            &close_fault,
            || {},
            |_file| Err(io::Error::other("injected close failure")),
        );
        assert!(result.is_err());
        assert_eq!(fs::read(close_fault).unwrap(), b"preserved");
    }

    #[cfg(unix)]
    #[cfg(any())]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn dir_swap_fails_closed_when_staging_identity_changes() {
        let root = tempdir().unwrap();
        let target = root.path().join("target");
        let staging = root.path().join("staging");
        let stolen = root.path().join("stolen");
        let attacker = root.path().join("attacker");
        fs::create_dir(&target).unwrap();
        fs::write(target.join("old"), b"old").unwrap();
        fs::create_dir(&staging).unwrap();
        fs::write(staging.join("new"), b"new").unwrap();
        fs::create_dir(&attacker).unwrap();
        fs::write(attacker.join("payload"), b"attacker").unwrap();

        let mut swap = DirSwap::new(&target, &staging).unwrap();
        let result = swap.commit_with_hook(|| {
            fs::rename(&staging, &stolen).unwrap();
            fs::rename(&attacker, &staging).unwrap();
        });

        assert!(result.is_err());
        assert_eq!(fs::read(target.join("old")).unwrap(), b"old");
        assert!(!target.join("payload").exists());
    }

    #[cfg(unix)]
    #[cfg(any())]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn dir_recovery_fails_closed_when_backup_identity_changes() {
        let root = tempdir().unwrap();
        let target = root.path().join("recover");
        let backup = root.path().join(".recover.symaira-backup-1");
        let stolen = root.path().join("stolen");
        let attacker = root.path().join("attacker");
        fs::create_dir(&backup).unwrap();
        fs::write(backup.join("expected"), b"expected").unwrap();
        fs::create_dir(&attacker).unwrap();
        fs::write(attacker.join("payload"), b"attacker").unwrap();

        let result = DirSwap::recover_with_hook(&target, || {
            fs::rename(&backup, &stolen).unwrap();
            fs::rename(&attacker, &backup).unwrap();
        });

        assert!(result.is_err());
        assert!(!target.exists());
    }

    #[cfg(unix)]
    #[cfg(any())]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn dir_swap_rollback_rejects_replaced_staging() {
        let root = tempdir().unwrap();
        let target = root.path().join("target");
        let staging = root.path().join("staging");
        let stolen = root.path().join("stolen");
        let attacker = root.path().join("attacker");
        fs::create_dir(&target).unwrap();
        fs::create_dir(&staging).unwrap();
        fs::create_dir(&attacker).unwrap();
        fs::write(attacker.join("payload"), b"attacker").unwrap();

        let mut swap = DirSwap::new(&target, &staging).unwrap();
        fs::rename(&staging, &stolen).unwrap();
        fs::rename(&attacker, &staging).unwrap();

        assert!(swap.rollback().is_err());
        assert_eq!(fs::read(staging.join("payload")).unwrap(), b"attacker");
        swap.committed = true;
    }

    #[cfg(unix)]
    #[cfg(any())]
    #[cfg_attr(miri, ignore = "Miri does not support capability filesystem syscalls")]
    #[test]
    fn dir_swap_rollback_rejects_replaced_backup() {
        let root = tempdir().unwrap();
        let target = root.path().join("target");
        let staging = root.path().join("staging");
        let stolen = root.path().join("stolen");
        let attacker = root.path().join("attacker");
        fs::create_dir(&target).unwrap();
        fs::create_dir(&staging).unwrap();
        fs::create_dir(&attacker).unwrap();
        fs::write(attacker.join("payload"), b"attacker").unwrap();

        let mut swap = DirSwap::new(&target, &staging).unwrap();
        fs::rename(&target, &swap.backup).unwrap();
        fs::rename(&swap.backup, &stolen).unwrap();
        fs::rename(&attacker, &swap.backup).unwrap();

        assert!(swap.rollback().is_err());
        assert!(!target.exists());
        assert_eq!(fs::read(swap.backup.join("payload")).unwrap(), b"attacker");
        swap.committed = true;
    }

    #[cfg_attr(miri, ignore = "Miri does not support filesystem locking")]
    #[test]
    fn lock_is_nonblocking() {
        let d = tempdir().unwrap();
        let p = d.path().join("l");
        let a = FileLock::try_lock(&p).unwrap();
        assert!(FileLock::try_lock(&p).is_err());
        drop(a);
        FileLock::try_lock(p).unwrap();
    }
}
