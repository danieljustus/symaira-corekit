//! Download and install a release using the Go updateapply ordering.
use crate::apply::{self, BinaryValidator};
use crate::cosign;
use crate::extract;
use crate::install_method;
use crate::request::secure_download_client_builder;
use crate::{Asset, Release};
use reqwest::blocking::{Client, Response};
use sha2::{Digest, Sha256};
use std::fmt::Write as _;
use std::fs::{self, DirBuilder, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

const MAX_ASSET_BODY: u64 = 1 << 30;
const DOWNLOAD_TIMEOUT: Duration = Duration::from_secs(15 * 60);
static TEMP_ID: AtomicU64 = AtomicU64::new(0);

/// The optional Go updateapply features, plus a replaceable HTTP client for
/// isolated consumers. Without an override, downloads require TLS 1.3 and
/// refuse redirects away from GitHub hosts.
pub struct Applier<'a> {
    pub goos: &'a str,
    pub goarch: &'a str,
    pub binary_name: Option<&'a str>,
    pub check_install_method: bool,
    pub cosign: Option<&'a cosign::Config<'a>>,
    pub extract_binary: Option<&'a str>,
    pub client: Option<Client>,
}

impl Default for Applier<'_> {
    fn default() -> Self {
        Self {
            goos: match std::env::consts::OS {
                "macos" => "darwin",
                other => other,
            },
            goarch: match std::env::consts::ARCH {
                "x86_64" => "amd64",
                "aarch64" => "arm64",
                other => other,
            },
            binary_name: None,
            check_install_method: false,
            cosign: None,
            extract_binary: None,
            client: None,
        }
    }
}

impl Applier<'_> {
    /// Apply one release. All fallible verification precedes the rename; an
    /// optional validator runs after the rename while the old binary is backed up.
    ///
    /// # Errors
    /// Rejects missing assets, unsafe installs, failed downloads, signatures,
    /// checksums, extraction, filesystem operations and failed validation.
    pub fn apply(
        &self,
        release: &Release,
        target: &Path,
        mut progress: Option<&mut dyn FnMut(u64, u64)>,
        validate: Option<BinaryValidator<'_>>,
    ) -> Result<(), String> {
        if target.to_string_lossy().trim().is_empty() {
            return Err("updateapply: targetPath is empty".into());
        }
        let binary_name = self.binary_name.unwrap_or_else(|| {
            target
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("")
        });
        if self.check_install_method {
            let method = install_method::detect(target)
                .map_err(|error| format!("updateapply: detect install method: {error}"))?;
            if !method.self_update_supported() {
                return Err(format!(
                    "updateapply: self-update is not supported for {} installation — {}",
                    method.as_str(),
                    method.guidance(binary_name)
                ));
            }
        }
        let asset =
            apply::select_asset(&release.assets, self.goos, self.goarch).ok_or_else(|| {
                format!(
                    "updateapply: no release asset matches {}/{}",
                    self.goos, self.goarch
                )
            })?;
        let checksum_asset = release
            .assets
            .iter()
            .find(|asset| asset.name.to_ascii_lowercase().contains("checksums"))
            .ok_or("updateapply: fetch checksums: release has no checksums.txt asset")?;
        let mut checksums_body = self
            .download(checksum_asset)
            .map_err(|error| format!("updateapply: fetch checksums: {error}"))?;
        let mut checksums_bytes = Vec::new();
        (&mut checksums_body)
            .take(MAX_ASSET_BODY + 1)
            .read_to_end(&mut checksums_bytes)
            .map_err(|error| {
                format!("updateapply: fetch checksums: read checksums.txt: {error}")
            })?;
        if checksums_bytes.len() as u64 > MAX_ASSET_BODY {
            return Err("updateapply: fetch checksums: checksums.txt exceeds 1 GiB".into());
        }
        let checksums = apply::parse_checksums(&checksums_bytes)
            .map_err(|error| format!("updateapply: fetch checksums: {error}"))?;
        if let Some(config) = self.cosign {
            let sig = config
                .fetch_signature(&release.tag_name)
                .map_err(|error| format!("updateapply: fetch cosign signature: {error}"))?;
            let cert = config
                .fetch_certificate(&release.tag_name)
                .map_err(|error| format!("updateapply: fetch cosign certificate: {error}"))?;
            config
                .verify_signature(&checksums_bytes, &sig, &cert)
                .map_err(|error| format!("updateapply: cosign verification failed: {error}"))?;
        }
        let wanted = checksums
            .get(&asset.name)
            .ok_or_else(|| format!("updateapply: no checksum entry for asset {:?}", asset.name))?;
        let target = std::path::absolute(target)
            .map_err(|error| format!("updateapply: resolve target path: {error}"))?;
        apply::check_writable(&target).map_err(|error| format!("updateapply: {error}"))?;
        let parent = target.parent().ok_or("updateapply: target has no parent")?;
        let mut stage = Staging::file(parent)?;
        let mut response = self
            .download(asset)
            .map_err(|error| format!("updateapply: download asset: {error}"))?;
        let total = response.content_length().unwrap_or(0);
        let mut written = 0u64;
        let mut digest = Sha256::new();
        let mut chunk = [0u8; 32 * 1024];
        loop {
            let count = (&mut response)
                .take((MAX_ASSET_BODY + 1).saturating_sub(written))
                .read(&mut chunk)
                .map_err(|error| {
                    format!("updateapply: download asset: read asset body: {error}")
                })?;
            if count == 0 {
                break;
            }
            if written + count as u64 > MAX_ASSET_BODY {
                return Err("updateapply: download asset: asset exceeds 1 GiB".into());
            }
            stage
                .file
                .as_mut()
                .expect("staging file remains open until download completes")
                .write_all(&chunk[..count])
                .map_err(|error| {
                    format!("updateapply: download asset: write temp file: {error}")
                })?;
            digest.update(&chunk[..count]);
            written += count as u64;
            if let Some(callback) = progress.as_mut() {
                callback(written, total);
            }
        }
        stage.file.take();
        if total > 0 && written != total {
            return Err(format!(
                "updateapply: download asset: incomplete download: got {written} bytes, want {total}"
            ));
        }
        let mut got = String::with_capacity(64);
        for byte in digest.finalize() {
            write!(got, "{byte:02x}").expect("formatting into String cannot fail");
        }
        if !got.eq_ignore_ascii_case(wanted) {
            return Err(format!(
                "updateapply: checksum mismatch for {:?}: got {got}, want {wanted}",
                asset.name
            ));
        }
        let extracted;
        let install = if let Some(binary) = self.extract_binary.filter(|name| !name.is_empty()) {
            extracted = Staging::directory(parent)?;
            let data = fs::read(&stage.path)
                .map_err(|error| format!("updateapply: read downloaded archive: {error}"))?;
            extract::extract_binary_to_dir(&data, &asset.name, &extracted.path, binary).map_err(
                |error| format!("updateapply: extract binary {binary:?} from archive: {error}"),
            )?
        } else {
            stage.path.clone()
        };
        make_executable(&install)
            .map_err(|error| format!("updateapply: make downloaded asset executable: {error}"))?;
        apply::atomic_swap(&install, &target, validate)
    }

    fn download(&self, asset: &Asset) -> Result<Response, String> {
        let default_client;
        let client = if let Some(client) = self.client.as_ref() {
            client
        } else {
            default_client = secure_download_client_builder(DOWNLOAD_TIMEOUT)
                .build()
                .map_err(|error| format!("request asset: {error}"))?;
            &default_client
        };
        let response = client
            .get(&asset.browser_download_url)
            .send()
            .map_err(|error| format!("request asset: {error}"))?;
        if response.status() != reqwest::StatusCode::OK {
            return Err(format!(
                "download {:?}: HTTP {}",
                asset.name,
                response.status().as_u16()
            ));
        }
        Ok(response)
    }
}

struct Staging {
    path: PathBuf,
    file: Option<File>,
    directory: bool,
}

impl Staging {
    fn file(parent: &Path) -> Result<Self, String> {
        for _ in 0..8 {
            let path = unique_path(parent, "updateapply")?;
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            match options.open(&path) {
                Ok(file) => {
                    return Ok(Self {
                        path,
                        file: Some(file),
                        directory: false,
                    });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => {
                    return Err(format!(
                        "updateapply: download asset: create temp file: {error}"
                    ));
                }
            }
        }
        Err("updateapply: download asset: no unique temp file available".into())
    }

    fn directory(parent: &Path) -> Result<Self, String> {
        for _ in 0..8 {
            let path = unique_path(parent, "updateapply-extract")?;
            #[cfg(unix)]
            let mut builder = DirBuilder::new();
            #[cfg(not(unix))]
            let builder = DirBuilder::new();
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            match builder.create(&path) {
                Ok(()) => {
                    return Ok(Self {
                        path,
                        file: None,
                        directory: true,
                    });
                }
                Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(format!("updateapply: create extract temp dir: {error}")),
            }
        }
        Err("updateapply: create extract temp dir: no unique path available".into())
    }
}

impl Drop for Staging {
    fn drop(&mut self) {
        self.file.take();
        if self.directory {
            let _ = fs::remove_dir_all(&self.path);
        } else {
            let _ = fs::remove_file(&self.path);
        }
    }
}

fn unique_path(parent: &Path, prefix: &str) -> Result<PathBuf, String> {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| format!("updateapply: create staging path: {error}"))?
        .as_nanos();
    let id = TEMP_ID.fetch_add(1, Ordering::Relaxed);
    Ok(parent.join(format!("{prefix}-{}-{timestamp}-{id}", std::process::id())))
}

#[cfg(unix)]
fn make_executable(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o755))
}

#[cfg(not(unix))]
// On Windows this clears the readonly attribute; Unix mode bits are not involved.
#[allow(clippy::permissions_set_readonly_false)]
fn make_executable(path: &Path) -> std::io::Result<()> {
    let mut permissions = fs::metadata(path)?.permissions();
    permissions.set_readonly(false);
    fs::set_permissions(path, permissions)
}
