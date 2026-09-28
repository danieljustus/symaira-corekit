#![deny(unsafe_code)]

//! Stable release-version decisions shared by update consumers.
//! Network, cache, archive, signature and installation contracts remain unported.

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
