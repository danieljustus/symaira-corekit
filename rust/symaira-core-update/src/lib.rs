#![deny(unsafe_code)]

//! Version decisions, response mapping, install-method detection, response
//! caching and archive extraction shared by update consumers. The signature,
//! download transport and atomic installation seams remain unported.

pub mod cache;
pub mod cosign_contract;
pub mod extract;
pub mod install_method;

pub mod request;

/// Whether the running version is a stable release eligible for an update check.
/// Invalid versions return before the Go checker performs HTTP or cache access.
#[must_use]
pub fn checkable(current: &str) -> bool {
    parse_stable(current).is_some()
}

/// Returns whether a stable release is newer than the running version.
/// Invalid running versions suppress checks; invalid release tags are errors.
/// A v0 consumer never offers a v1+ release automatically.
///
/// # Errors
/// Returns an error when a fetched release tag is not a stable version.
pub fn update_available(current: &str, latest: &str) -> Result<bool, &'static str> {
    let Some(current) = parse_stable(current) else {
        return Ok(false);
    };
    let latest =
        parse_stable(latest).ok_or("latest release tag is not a stable semantic version")?;
    Ok(latest > current && !(current.0 == 0 && latest.0 > 0))
}

/// Release asset returned by the Go update checker.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Asset {
    pub name: String,
    pub browser_download_url: String,
    pub size: i64,
}

/// Release metadata returned when an update is available.
#[derive(Debug, PartialEq, Eq)]
pub struct Release {
    pub tag_name: String,
    pub body: String,
    pub html_url: String,
    pub assets: Vec<Asset>,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Response {
    pub draft: bool,
    pub html_url: String,
    pub prerelease: bool,
    pub tag_name: String,
    pub body: String,
    pub assets: Vec<Asset>,
}

/// Applies the Go checker's response eligibility and release mapping to one
/// already-decoded response. Network, JSON decoding, cache and TLS behavior
/// remain outside this slice.
///
/// # Errors
/// Returns the Go response eligibility or malformed-tag error text.
pub fn check_response(current: &str, response: Response) -> Result<Option<Release>, String> {
    if !checkable(current) {
        return Ok(None);
    }
    if response.draft {
        return Err("latest release response returned a draft release".to_owned());
    }
    if response.prerelease {
        return Err("latest release response returned a prerelease".to_owned());
    }
    if response.tag_name.trim().is_empty() {
        return Err("latest release response did not include a tag name".to_owned());
    }
    let tag_name = response.tag_name.trim().to_owned();
    let Some(latest) = parse_stable(&tag_name) else {
        return Err(format!(
            "latest release tag {tag_name:?} is not a stable semantic version"
        ));
    };
    let current = parse_stable(current).expect("checkable current version");
    if latest <= current || (current.0 == 0 && latest.0 > 0) {
        return Ok(None);
    }
    Ok(Some(Release {
        tag_name,
        body: response.body,
        html_url: response.html_url.trim().to_owned(),
        assets: response.assets,
    }))
}

fn parse_stable(raw: &str) -> Option<(isize, isize, isize)> {
    let trimmed = raw.trim().strip_prefix('v').unwrap_or(raw.trim());
    if trimmed.contains(['-', '+']) {
        return None;
    }
    let mut parts = trimmed.split('.');
    let major = parts.next()?.parse::<isize>().ok()?;
    let minor = parts.next()?.parse::<isize>().ok()?;
    let patch = parts.next()?.parse::<isize>().ok()?;
    if parts.next().is_some() || major < 0 || minor < 0 || patch < 0 {
        return None;
    }
    Some((major, minor, patch))
}
