//! Synchronous public release checker. Cancellation remains a separate API slice.
use crate::{Release, cache, check_response, checkable, request};
use sha2::{Digest, Sha256};
use std::{
    path::PathBuf,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

/// Metadata timeout of the Go secure client.
pub const DEFAULT_API_TIMEOUT: Duration = Duration::from_secs(3);

/// Consumer-provided synchronous transport. The default uses hardened HTTP.
/// Implementations must enforce their own timeout and redirect/TLS policies.
pub type Transport =
    Box<dyn Fn(&str, &str) -> Result<request::Response, request::Error> + Send + Sync>;

/// A GitHub release checker with independently configurable endpoint and cache.
pub struct Checker {
    pub latest_release_url: String,
    pub cache_path: PathBuf,
    pub cache_ttl: Duration,
    pub transport: Option<Transport>,
    default_url: String,
    default_cache_path: PathBuf,
    cached: Option<(SystemTime, Release)>,
}

/// Stable, traversal-safe cache identity, matching Go's owner-NUL-repo hash.
#[must_use]
pub fn default_cache_path(owner: &str, repo: &str) -> PathBuf {
    let base = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .unwrap_or_else(|| {
            std::env::var_os(if cfg!(windows) { "USERPROFILE" } else { "HOME" })
                .filter(|home| !home.is_empty())
                .map_or_else(
                    || PathBuf::from(".cache"),
                    |home| PathBuf::from(home).join(".cache"),
                )
        });
    let mut hash = Sha256::new();
    hash.update(owner.as_bytes());
    hash.update([0]);
    hash.update(repo.as_bytes());
    let identity: String = hash
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    base.join("symaira/updatecheck")
        .join(format!("{identity}.json"))
}

impl Checker {
    #[must_use]
    pub fn new(owner: &str, repo: &str) -> Self {
        let url = format!("https://api.github.com/repos/{owner}/{repo}/releases/latest");
        let path = default_cache_path(owner, repo);
        Self {
            latest_release_url: url.clone(),
            default_url: url,
            cache_path: path.clone(),
            default_cache_path: path,
            cache_ttl: cache::DEFAULT_CACHE_TTL,
            transport: None,
            cached: None,
        }
    }

    /// Returns an eligible newer release, conditioned on the running version.
    /// # Errors
    /// Returns transport, JSON decoding or release-validation errors.
    pub fn check(&mut self, current: &str) -> Result<Option<Release>, String> {
        self.check_with_force(current, false)
    }

    /// Force bypasses both caches. Invalid current versions touch neither cache nor HTTP.
    /// # Errors
    /// Returns transport, JSON decoding or release-validation errors.
    pub fn check_with_force(
        &mut self,
        current: &str,
        force: bool,
    ) -> Result<Option<Release>, String> {
        if !checkable(current) {
            return Ok(None);
        }
        let now = SystemTime::now();
        if !force {
            if self.cached.is_none()
                && self.should_persist()
                && let Some((created, cached)) = cache::read_cache(&self.cache_path)
                && let Ok(response) = cache::decode_release(&cached.response, true)
                && crate::checkable(&response.tag_name)
            {
                self.cached = Some((
                    UNIX_EPOCH + Duration::from_millis(u64::try_from(created).unwrap_or(u64::MAX)),
                    Release {
                        tag_name: response.tag_name,
                        body: response.body,
                        html_url: response.html_url,
                        assets: response.assets,
                    },
                ));
            }
            if let Some((created, release)) = &self.cached
                && now
                    .duration_since(*created)
                    .map_or(true, |elapsed| elapsed < self.cache_ttl)
                && crate::checkable(&release.tag_name)
            {
                return select(current, release);
            }
        }
        let response = if let Some(transport) = &self.transport {
            transport(self.latest_release_url.trim(), current)
        } else {
            request::fetch(&self.latest_release_url, current, DEFAULT_API_TIMEOUT)
        }
        .map_err(|error| error.message)?;
        if response.status != 200 {
            return Err(format!("GitHub API returned HTTP {}", response.status));
        }
        let raw = String::from_utf8(response.body.into_iter().take(1 << 20).collect())
            .map_err(|error| format!("decode latest release response: {error}"))?;
        let decoded = cache::decode_release(&raw, false)?;
        // Validate before caching, independently of current-version selection.
        check_response(
            current,
            crate::Response {
                draft: decoded.draft,
                prerelease: decoded.prerelease,
                tag_name: decoded.tag_name.clone(),
                ..crate::Response::default()
            },
        )?;
        let release = Release {
            tag_name: decoded.tag_name.trim().to_owned(),
            body: decoded.body,
            html_url: decoded.html_url.trim().to_owned(),
            assets: decoded.assets,
        };
        let now = SystemTime::now();
        if self.should_persist() {
            let _ = cache::write_cache(
                &self.cache_path,
                now.duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis(),
                &cache::CachedRelease {
                    tag_name: release.tag_name.clone(),
                    response: raw,
                },
            );
        }
        let selected = select(current, &release);
        self.cached = Some((now, release));
        selected
    }

    fn should_persist(&self) -> bool {
        !self.cache_path.as_os_str().is_empty()
            && (self.latest_release_url == self.default_url
                || self.cache_path != self.default_cache_path)
    }
}

fn select(current: &str, release: &Release) -> Result<Option<Release>, String> {
    if crate::update_available(current, &release.tag_name).map_err(str::to_owned)? {
        Ok(Some(release.clone()))
    } else {
        Ok(None)
    }
}
