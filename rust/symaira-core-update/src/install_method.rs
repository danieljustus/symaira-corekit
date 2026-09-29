//! Install method detection and update guidance shared with the Go API.
use std::collections::HashMap;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum InstallMethod {
    DirectDownload,
    Homebrew,
    GoInstall,
    PackageManager,
    BuildFromSource,
    Unknown,
}

impl InstallMethod {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DirectDownload => "direct-download",
            Self::Homebrew => "homebrew",
            Self::GoInstall => "go-install",
            Self::PackageManager => "package-manager",
            Self::BuildFromSource => "build-from-source",
            Self::Unknown => "unknown",
        }
    }

    #[must_use]
    pub const fn self_update_supported(self) -> bool {
        matches!(self, Self::DirectDownload)
    }

    #[must_use]
    pub fn guidance(self, tool_name: &str) -> String {
        match self {
            Self::DirectDownload => {
                "Re-run the quick install script or download the latest release from GitHub".into()
            }
            Self::Homebrew => format!("Update via Homebrew: brew update && brew upgrade {tool_name}"),
            Self::GoInstall => format!("Update via Go: go install github.com/danieljustus/{tool_name}@latest"),
            Self::PackageManager => "Update via your system package manager (e.g., apt upgrade, yum update, pacman -Syu)".into(),
            Self::BuildFromSource => "Rebuild from source: git pull && go build".into(),
            Self::Unknown => "Unable to determine installation method. Reinstall from the GitHub releases page".into(),
        }
    }
}

/// Detects an install method using the current process environment.
pub fn detect(binary_path: &Path) -> Result<InstallMethod, &'static str> {
    let env: HashMap<String, String> = [
        "HOMEBREW_PREFIX",
        "GOPATH",
        "GOMODCACHE",
        "HOME",
        "USERPROFILE",
    ]
    .into_iter()
    .filter_map(|key| env::var(key).ok().map(|value| (key.to_owned(), value)))
    .collect();
    let home_key = if cfg!(windows) { "USERPROFILE" } else { "HOME" };
    let home = env::var_os(home_key)
        .filter(|value| !value.is_empty())
        .map(PathBuf::from);
    detect_with(binary_path, &env, home.as_deref())
}

/// Detects an install method against an explicit environment for reproducible callers.
pub fn detect_with(
    binary_path: &Path,
    environment: &HashMap<String, String>,
    home: Option<&Path>,
) -> Result<InstallMethod, &'static str> {
    if binary_path.as_os_str().is_empty() {
        return Err("binary path must not be empty");
    }
    let resolved = fs::canonicalize(binary_path);
    let canonical_binary = resolved.is_ok();
    let real_path = resolved.unwrap_or_else(|_| binary_path.to_owned());
    let absolute = if real_path.is_absolute() {
        real_path
    } else {
        env::current_dir().unwrap_or_default().join(real_path)
    };
    let absolute = absolute.to_string_lossy();

    let env_path = |key: &str| -> Option<String> {
        let value = environment.get(key)?;
        if value.is_empty() {
            return None;
        }
        let resolved = fs::canonicalize(value).unwrap_or_else(|_| PathBuf::from(value));
        Some(resolved.to_string_lossy().into_owned())
    };
    if let Some(prefix) = env_path("HOMEBREW_PREFIX")
        && absolute.starts_with(&prefix)
    {
        return Ok(InstallMethod::Homebrew);
    }
    if let Some(gopath) = env_path("GOPATH")
        && absolute.starts_with(&Path::new(&gopath).join("bin").to_string_lossy().to_string())
    {
        return Ok(InstallMethod::GoInstall);
    }
    if let Some(cache) = env_path("GOMODCACHE")
        && absolute.starts_with(&cache)
    {
        return Ok(InstallMethod::GoInstall);
    }

    if ["/opt/homebrew/", "/usr/local/Cellar/", "/.linuxbrew/"]
        .iter()
        .any(|pattern| absolute.contains(pattern))
    {
        return Ok(InstallMethod::Homebrew);
    }
    if absolute.starts_with("/usr/bin/") {
        return Ok(InstallMethod::PackageManager);
    }
    if absolute.starts_with("/usr/local/bin/") {
        return Ok(InstallMethod::DirectDownload);
    }
    if let Some(gopath) = env_path("GOPATH") {
        let bin = format!(
            "{}{}",
            Path::new(&gopath).join("bin").display(),
            std::path::MAIN_SEPARATOR
        );
        if absolute.starts_with(&bin) {
            return Ok(InstallMethod::GoInstall);
        }
    }
    if let Some(home) = home {
        // Windows canonicalization introduces a verbatim prefix. Match it only
        // when the binary was also canonicalized; nonexistent fixture paths
        // must retain their lexical home, as must the Unix Go contract.
        let home = if cfg!(windows) && canonical_binary {
            fs::canonicalize(home).unwrap_or_else(|_| home.to_owned())
        } else {
            home.to_owned()
        };
        let go_bin = format!(
            "{}{}",
            home.join("go").join("bin").display(),
            std::path::MAIN_SEPARATOR
        );
        if absolute.starts_with(&go_bin) {
            return Ok(InstallMethod::GoInstall);
        }
        for dir in [
            home.join("bin"),
            home.join(".local").join("bin"),
            home.join(".cargo").join("bin"),
        ] {
            let prefix = format!("{}{}", dir.display(), std::path::MAIN_SEPARATOR);
            if absolute.starts_with(&prefix) {
                return Ok(InstallMethod::DirectDownload);
            }
        }
    }

    if absolute.contains("/Cellar/") {
        return Ok(InstallMethod::Homebrew);
    }
    let base = Path::new(absolute.as_ref()).file_name().unwrap_or_default();
    if Path::new("/var/lib/dpkg/info")
        .join(format!("{}.list", base.to_string_lossy()))
        .exists()
    {
        return Ok(InstallMethod::PackageManager);
    }
    if absolute.contains('@') || absolute.contains("/pkg/mod/") {
        return Ok(InstallMethod::GoInstall);
    }
    if cfg!(windows) {
        return Ok(InstallMethod::BuildFromSource);
    }
    let dir = Path::new(absolute.as_ref())
        .parent()
        .unwrap_or_else(|| Path::new("."));
    let Ok(metadata) = fs::metadata(dir) else {
        return Ok(InstallMethod::Unknown);
    };
    let mode = permissions_mode(&metadata);
    if mode & 0o200 != 0 || mode & 0o022 != 0 {
        Ok(InstallMethod::DirectDownload)
    } else {
        Ok(InstallMethod::BuildFromSource)
    }
}

#[cfg(unix)]
fn permissions_mode(metadata: &fs::Metadata) -> u32 {
    use std::os::unix::fs::PermissionsExt;
    metadata.permissions().mode()
}

#[cfg(not(unix))]
fn permissions_mode(metadata: &fs::Metadata) -> u32 {
    if metadata.permissions().readonly() {
        0
    } else {
        0o200
    }
}
