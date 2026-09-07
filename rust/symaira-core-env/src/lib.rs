#![deny(unsafe_code)]

//! Ordered environment-variable lookup helpers.

use std::env;
use std::io;

/// Return the first non-empty value from the primary name and ordered aliases.
pub fn getenv(primary: &str, legacy: &[&str]) -> Option<String> {
    std::iter::once(primary)
        .chain(legacy.iter().copied())
        .find_map(|name| env::var(name).ok().filter(|value| !value.is_empty()))
}

/// Go-compatible spelling: return an empty string when no value is present.
pub fn getenv_lossy(primary: &str, legacy: &[&str]) -> String {
    getenv(primary, legacy).unwrap_or_default()
}

/// Remove an environment variable in an owned environment map.
///
/// Rust 2024 makes mutation of the process environment unsafe because it can
/// race with foreign threads. This safe crate therefore exposes the operation
/// through [`Environment`] instead of using an unsafe process-global mutation.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct Environment {
    values: std::collections::BTreeMap<String, String>,
}

impl Environment {
    pub fn from_pairs<I, K, V>(values: I) -> Self
    where
        I: IntoIterator<Item = (K, V)>,
        K: Into<String>,
        V: Into<String>,
    {
        Self {
            values: values
                .into_iter()
                .map(|(key, value)| (key.into(), value.into()))
                .collect(),
        }
    }

    pub fn getenv(&self, primary: &str, legacy: &[&str]) -> Option<&str> {
        std::iter::once(primary)
            .chain(legacy.iter().copied())
            .find_map(|name| {
                self.values
                    .get(name)
                    .map(String::as_str)
                    .filter(|value| !value.is_empty())
            })
    }

    pub fn get(&self, key: &str) -> Option<&str> {
        self.values.get(key).map(String::as_str)
    }

    pub fn unsetenv(&mut self, key: &str) -> io::Result<()> {
        self.values.remove(key);
        Ok(())
    }

    pub fn is_absent(&self, key: &str) -> bool {
        !self.values.contains_key(key)
    }
}

/// Remove a variable from the process environment.
///
/// # Safety
///
/// The caller must establish that no other thread (including foreign code) is
/// concurrently reading or mutating the process environment for the duration
/// of this call. Rust 2024 marks process-environment mutation unsafe because
/// the platform environment is process-global and is not synchronized with
/// arbitrary readers. Prefer [`Environment`] for ordinary application code.
#[allow(unsafe_code)]
pub unsafe fn unsetenv(key: &str) -> io::Result<()> {
    if key.is_empty() || key.contains('=') || key.contains('\0') {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "invalid environment variable name",
        ));
    }
    // SAFETY: The precondition above is the narrow contract required by
    // `std::env::remove_var`; callers must also uphold this function's
    // documented no-concurrent-environment-access contract.
    unsafe { env::remove_var(key) };
    Ok(())
}
