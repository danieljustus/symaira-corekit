//! Execute the Go update verifier's keyless Cosign command over exact checksum bytes.
use crate::cosign_contract::identity_regexp;
use crate::request::secure_download_client_builder;
use reqwest::blocking::Client;
use std::error::Error as _;
use std::fs::{self, DirBuilder, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use std::time::{SystemTime, UNIX_EPOCH};

const ISSUER: &str = "https://token.actions.githubusercontent.com";
const MAX_ARTIFACT_BODY: u64 = 1 << 20;
static TEMP_ID: AtomicU64 = AtomicU64::new(0);

/// Repository-specific release signature settings.
pub struct Config<'a> {
    pub repo: &'a str,
    pub binary_name: &'a str,
    pub download_base_url: Option<&'a str>,
    pub identity_regexp: Option<&'a str>,
}

impl Config<'_> {
    /// Fetch the signature of the release checksums, not the asset itself.
    ///
    /// # Errors
    /// Rejects non-HTTPS URLs, failed requests and bodies above one MiB.
    pub fn fetch_signature(&self, version: &str) -> Result<Vec<u8>, String> {
        self.fetch_artifact(version, "sig", "signature")
    }

    /// Fetch the release certificate from the same trusted transport.
    ///
    /// # Errors
    /// Rejects non-HTTPS URLs, failed requests and bodies above one MiB.
    pub fn fetch_certificate(&self, version: &str) -> Result<Vec<u8>, String> {
        self.fetch_artifact(version, "pem", "certificate")
    }

    fn fetch_artifact(
        &self,
        version: &str,
        extension: &str,
        label: &str,
    ) -> Result<Vec<u8>, String> {
        let parsed = self.artifact_url(version, extension, label)?;
        let client = secure_download_client_builder(Duration::from_secs(3))
            .build()
            .map_err(|error| format!("fetch cosign {label}: {error}"))?;
        self.fetch_artifact_with_client(&client, parsed, label)
    }

    fn artifact_url(
        &self,
        version: &str,
        extension: &str,
        label: &str,
    ) -> Result<reqwest::Url, String> {
        let version = version.strip_prefix('v').unwrap_or(version);
        if version.is_empty() {
            return Err("version must not be empty".into());
        }
        let default_base = format!("https://github.com/{}/releases/download", self.repo);
        let base = self.download_base_url.unwrap_or(&default_base);
        let url = format!(
            "{base}/v{version}/{}_{version}_checksums.txt.{extension}",
            self.binary_name
        );
        let parsed = reqwest::Url::parse(&url)
            .map_err(|error| format!("invalid cosign {label} URL: {error}"))?;
        if parsed.scheme() != "https" {
            return Err(format!(
                "cosign {label} URL must use HTTPS, got {:?}",
                parsed.scheme()
            ));
        }
        Ok(parsed)
    }

    fn fetch_artifact_with_client(
        &self,
        client: &Client,
        url: reqwest::Url,
        label: &str,
    ) -> Result<Vec<u8>, String> {
        let mut response = client.get(url).send().map_err(|error| {
            let mut cause = error.source();
            while let Some(source) = cause {
                let reason = source.to_string();
                if reason.starts_with("refusing redirect to non-GitHub host")
                    || reason.starts_with("refusing redirect to non-HTTPS scheme")
                    || reason == "stopped after 10 redirects"
                {
                    return format!("fetch cosign {label}: {error}: {reason}");
                }
                cause = source.source();
            }
            format!("fetch cosign {label}: {error}")
        })?;
        if response.status() != reqwest::StatusCode::OK {
            return Err(format!(
                "fetch cosign {label}: HTTP {}",
                response.status().as_u16()
            ));
        }
        let mut body = Vec::new();
        (&mut response)
            .take(MAX_ARTIFACT_BODY + 1)
            .read_to_end(&mut body)
            .map_err(|error| format!("read cosign {label} response: {error}"))?;
        if body.len() as u64 > MAX_ARTIFACT_BODY {
            return Err(format!(
                "cosign {label} exceeds maximum size of {MAX_ARTIFACT_BODY} bytes"
            ));
        }
        Ok(body)
    }

    /// Verify the unmodified downloaded manifest with its signature and certificate.
    ///
    /// # Errors
    /// Returns the Cosign process or filesystem failure; never silently skips verification.
    pub fn verify_signature(
        &self,
        content: &[u8],
        signature: &[u8],
        certificate: &[u8],
    ) -> Result<(), String> {
        verify_signature(
            self.repo,
            self.identity_regexp,
            content,
            signature,
            certificate,
        )
    }
}

struct PrivateDir(PathBuf);

impl Drop for PrivateDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn private_dir() -> Result<PrivateDir, String> {
    for _ in 0..8 {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(|error| format!("create temp directory: {error}"))?
            .as_nanos();
        let id = TEMP_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "cosign-verify-{}-{timestamp}-{id}",
            std::process::id()
        ));
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
            Ok(()) => return Ok(PrivateDir(path)),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(format!("create temp directory: {error}")),
        }
    }
    Err("create temp directory: no unique path available".into())
}

fn write_private(path: &Path, contents: &[u8], label: &str) -> Result<(), String> {
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(path)
        .map_err(|error| format!("write {label} file: {error}"))?;
    file.write_all(contents)
        .map_err(|error| format!("write {label} file: {error}"))
}

/// Verify exact downloaded checksum bytes with the installed Cosign CLI.
///
/// # Errors
/// Returns an error when Cosign is missing, rejects the identity, issuer or
/// signature, or when a temporary file cannot be written. Never accepts a
/// signature without the CLI's successful verification.
pub fn verify_signature(
    repo: &str,
    identity_override: Option<&str>,
    content: &[u8],
    signature: &[u8],
    certificate: &[u8],
) -> Result<(), String> {
    verify_with_executable(
        Path::new("cosign"),
        repo,
        identity_override,
        content,
        signature,
        certificate,
    )
}

fn verify_with_executable(
    executable: &Path,
    repo: &str,
    identity_override: Option<&str>,
    content: &[u8],
    signature: &[u8],
    certificate: &[u8],
) -> Result<(), String> {
    let temporary = private_dir()?;
    let content_path = temporary.0.join("content");
    let signature_path = temporary.0.join("signature.sig");
    let certificate_path = temporary.0.join("certificate.pem");
    write_private(&content_path, content, "content")?;
    write_private(&signature_path, signature, "signature")?;
    write_private(&certificate_path, certificate, "certificate")?;

    let pattern = identity_override
        .filter(|override_pattern| !override_pattern.is_empty())
        .map_or_else(|| identity_regexp(repo), str::to_owned);
    let output = Command::new(executable)
        .arg("verify-blob")
        .arg("--certificate")
        .arg(&certificate_path)
        .arg("--signature")
        .arg(&signature_path)
        .arg("--certificate-identity-regexp")
        .arg(pattern)
        .arg("--certificate-oidc-issuer")
        .arg(ISSUER)
        .arg(&content_path)
        .stdout(Stdio::null())
        .output()
        .map_err(|error| {
            if error.kind() == std::io::ErrorKind::NotFound {
                format!("cosign CLI not found — install cosign from https://docs.sigstore.dev to verify release signatures: {error}")
            } else {
                format!("cosign verify-blob failed: {error}")
            }
        })?;
    if output.status.success() {
        return Ok(());
    }
    Err(format!(
        "cosign verify-blob failed: {}: {}",
        String::from_utf8_lossy(&output.stderr).trim(),
        output.status
    ))
}

#[cfg(all(test, unix))]
mod tests {
    use super::{private_dir, verify_signature, verify_with_executable};
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;

    #[test]
    fn verifier_process_success_and_failure_are_not_confused() {
        let repo = "owner/repo";
        let args = (
            b"checksums\n".as_slice(),
            b"sig".as_slice(),
            b"cert".as_slice(),
        );
        let directory = private_dir().unwrap();
        let executable = directory.0.join("fixture-cosign");
        fs::write(
            &executable,
            r##"#!/bin/sh
[ "$#" -eq 10 ] && [ "$1" = verify-blob ] &&
[ "$2" = --certificate ] && [ "$(cat "$3")" = cert ] &&
[ "$4" = --signature ] && [ "$(cat "$5")" = sig ] &&
[ "$6" = --certificate-identity-regexp ] &&
[ "$7" = '^https://github\.com/owner/repo/\.github/workflows/release\.yml@refs/tags/v.*$' ] &&
[ "$8" = --certificate-oidc-issuer ] &&
[ "$9" = https://token.actions.githubusercontent.com ] &&
[ "$(cat "${10}")" = checksums ] && [ "$(wc -c < "${10}")" -eq 10 ]
"##,
        )
        .unwrap();
        fs::set_permissions(&executable, fs::Permissions::from_mode(0o700)).unwrap();
        verify_with_executable(&executable, repo, None, args.0, args.1, args.2)
            .expect("the fixture verified exact argv and input bytes");
        let rejected = verify_with_executable(
            Path::new("/usr/bin/false"),
            repo,
            None,
            args.0,
            args.1,
            args.2,
        );
        assert!(
            rejected
                .unwrap_err()
                .starts_with("cosign verify-blob failed:")
        );
    }

    #[test]
    #[ignore = "requires a locally installed Cosign CLI"]
    fn real_cosign_rejects_invalid_signature_and_certificate() {
        let error = verify_signature(
            "owner/repo",
            None,
            b"checksums\n",
            b"not-a-signature",
            b"not-a-certificate",
        )
        .unwrap_err();
        assert!(error.starts_with("cosign verify-blob failed:"), "{error}");
    }
}

#[cfg(test)]
mod network_tests {
    use super::Config;
    use crate::request::secure_download_client_builder;
    use reqwest::tls::Certificate;
    use serde_json::Value;
    use std::path::Path;
    use std::time::Duration;

    #[test]
    #[ignore = "requires the Go TLS 1.3 fixture server and fresh Cosign oracle"]
    fn cosign_artifact_fetch_replays_go_observations() {
        let fixture: Value = serde_json::from_slice(
            &std::fs::read(std::env::var("COSIGN_CONTRACT_FIXTURE").unwrap()).unwrap(),
        )
        .unwrap();
        let expected = |id: &str| {
            fixture["cases"]
                .as_array()
                .unwrap()
                .iter()
                .find(|case| case["id"] == id)
                .unwrap()["result"]
                .clone()
        };
        let server = std::env::var("UPDATE_REQUEST_TLS13_URL").unwrap();
        let certificate = Certificate::from_der(
            &std::fs::read(std::env::var("UPDATE_REQUEST_TLS13_CERT").unwrap()).unwrap(),
        )
        .unwrap();
        let client = secure_download_client_builder(Duration::from_secs(3))
            .tls_certs_only([certificate])
            .build()
            .unwrap();
        let base = format!("{server}/releases/download");
        let config = Config {
            repo: "owner/repo",
            binary_name: "tool",
            download_base_url: Some(&base),
            identity_regexp: None,
        };
        for (id, version, ext, label) in [
            ("fetch-signature", "v1.2.3", "sig", "signature"),
            ("fetch-certificate", "1.2.3", "pem", "certificate"),
        ] {
            let url = config.artifact_url(version, ext, label).unwrap();
            assert_eq!(
                format!("GET {}", url.path()),
                expected(id)["request"].as_str().unwrap(),
                "{id}"
            );
            let body = config
                .fetch_artifact_with_client(&client, url, label)
                .unwrap();
            assert_eq!(body, expected(id)["body"].as_str().unwrap().as_bytes());
        }
        for (id, version) in [("fetch-http-404", "404"), ("fetch-too-large", "large")] {
            let url = config.artifact_url(version, "sig", "signature").unwrap();
            let error = config
                .fetch_artifact_with_client(&client, url, "signature")
                .unwrap_err();
            assert_eq!(error, expected(id)["error_message"].as_str().unwrap());
        }
        let foreign = config.artifact_url("foreign", "sig", "signature").unwrap();
        let error = config
            .fetch_artifact_with_client(&client, foreign, "signature")
            .unwrap_err();
        assert!(
            error.contains("refusing redirect to non-GitHub host"),
            "{error}"
        );
        let downgrade = config
            .artifact_url("downgrade", "sig", "signature")
            .unwrap();
        let error = config
            .fetch_artifact_with_client(&client, downgrade, "signature")
            .unwrap_err();
        assert!(
            error.contains("refusing redirect to non-HTTPS scheme"),
            "{error}"
        );
        assert_eq!(
            config.fetch_signature("").unwrap_err(),
            expected("fetch-empty-version")["error_message"]
                .as_str()
                .unwrap()
        );
        let insecure = Config {
            download_base_url: Some("http://loopback/release"),
            ..config
        };
        assert_eq!(
            insecure.fetch_signature("1.2.3").unwrap_err(),
            expected("fetch-http-url")["error_message"]
                .as_str()
                .unwrap()
        );
    }

    #[test]
    #[ignore = "requires pinned symaira-vault release assets and a real Cosign CLI"]
    fn signed_release_accepts_exact_bytes_and_rejects_tampering() {
        let root = std::env::var("COSIGN_VALID_FIXTURE_DIR").unwrap();
        let root = Path::new(&root);
        let read_pinned = |suffix: &str, expected: &str| {
            let path = root.join(format!("symaira-vault_0.22.1_checksums.txt{suffix}"));
            let bytes = std::fs::read(path).unwrap();
            assert_eq!(crate::apply::sha256_hex(&bytes), expected);
            bytes
        };
        let content = read_pinned(
            "",
            "e722249e12a560717f67af31db4d5153186442a243aee1a14b2a42a02f97ee05",
        );
        let signature = read_pinned(
            ".sig",
            "2012a27ad4bf0a7ce080f04d04557a664f26987597b58af4a7be44a66166560f",
        );
        let certificate = read_pinned(
            ".pem",
            "32295da270034818625e04e51a0f8cd41796de3cf125cecf3e764e1f85c6b4a4",
        );
        let config = Config {
            repo: "danieljustus/symaira-vault",
            binary_name: "symaira-vault",
            download_base_url: None,
            identity_regexp: None,
        };
        assert_eq!(config.fetch_signature("v0.22.1").unwrap(), signature);
        assert_eq!(config.fetch_certificate("v0.22.1").unwrap(), certificate);
        config
            .verify_signature(&content, &signature, &certificate)
            .unwrap();
        let mut tampered = content.clone();
        tampered[0] ^= 1;
        assert!(
            config
                .verify_signature(&tampered, &signature, &certificate)
                .is_err()
        );
        let wrong_identity = Config {
            identity_regexp: Some("^not-the-release-workflow$"),
            ..config
        };
        assert!(
            wrong_identity
                .verify_signature(&content, &signature, &certificate)
                .is_err()
        );
    }
}
