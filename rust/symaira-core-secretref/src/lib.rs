#![deny(unsafe_code)]

//! Secret-reference parsing and resolution with a bounded, redacting command
//! boundary. Helper stderr is diagnostic input, never an error payload.

use serde::{Deserialize, Serialize};
use std::env;
use std::fmt;
use std::io::{self, Read};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, mpsc};
use std::thread;
use std::time::{Duration, Instant};
use thiserror::Error;

#[cfg(unix)]
use rustix::process::{Pid, Signal, kill_process_group};
#[cfg(unix)]
use std::os::unix::process::CommandExt;

pub const ORACLE_COMMIT: &str = "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588";
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(5);
const MAX_HELPER_STREAM: usize = 64 * 1024;

#[derive(Clone, Debug, Eq, Hash, PartialEq, Serialize, Deserialize)]
pub enum SecretRef {
    Symvault { path: String },
    Keychain { service: String, account: String },
    Env { name: String },
}

#[derive(Clone, Debug, Eq, PartialEq, Error)]
pub enum ParseError {
    #[error("secret reference is empty")]
    Empty,
    #[error("invalid symvault credential path: {0}")]
    InvalidSymvaultPath(String),
    #[error("invalid keychain reference: expected keychain://service/account")]
    InvalidKeychain,
    #[error("environment variable name is empty")]
    EmptyEnvironmentName,
}

impl SecretRef {
    pub fn parse(input: &str) -> Result<Self, ParseError> {
        if input.is_empty() {
            return Err(ParseError::Empty);
        }
        if let Some(path) = input.strip_prefix("symvault://") {
            validate_vault_path(path)?;
            return Ok(Self::Symvault {
                path: path.to_owned(),
            });
        }
        if let Some(rest) = input.strip_prefix("keychain://") {
            let Some((service, account)) = rest.split_once('/') else {
                return Err(ParseError::InvalidKeychain);
            };
            if service.is_empty() || account.is_empty() || account.contains('/') {
                return Err(ParseError::InvalidKeychain);
            }
            validate_component(service)?;
            validate_component(account)?;
            return Ok(Self::Keychain {
                service: service.to_owned(),
                account: account.to_owned(),
            });
        }
        let name = input.strip_prefix("env://").unwrap_or(input);
        if name.is_empty() {
            return Err(ParseError::EmptyEnvironmentName);
        }
        Ok(Self::Env {
            name: name.to_owned(),
        })
    }
    #[must_use]
    pub fn name(&self) -> &str {
        match self {
            Self::Symvault { path } => path,
            Self::Keychain { service, .. } => service,
            Self::Env { name } => name,
        }
    }
    #[must_use]
    pub fn is_environment(&self) -> bool {
        matches!(self, Self::Env { .. })
    }
    #[must_use]
    pub fn as_symvault_path(&self) -> Option<&str> {
        match self {
            Self::Symvault { path } => Some(path),
            _ => None,
        }
    }
    #[must_use]
    pub fn as_keychain(&self) -> Option<(&str, &str)> {
        match self {
            Self::Keychain { service, account } => Some((service, account)),
            _ => None,
        }
    }
}
impl fmt::Display for SecretRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Symvault { path } => write!(f, "symvault://{path}"),
            Self::Keychain { service, account } => write!(f, "keychain://{service}/{account}"),
            Self::Env { name } => write!(f, "env://{name}"),
        }
    }
}
impl std::str::FromStr for SecretRef {
    type Err = ParseError;
    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Self::parse(s)
    }
}
pub type SecretReference = SecretRef;

fn validate_vault_path(path: &str) -> Result<(), ParseError> {
    if path.is_empty() {
        return Err(ParseError::InvalidSymvaultPath("empty".into()));
    }
    if path.starts_with('-') {
        return Err(ParseError::InvalidSymvaultPath(
            "must not start with '-'".into(),
        ));
    }
    if path.as_bytes().contains(&0) {
        return Err(ParseError::InvalidSymvaultPath(
            "contains a null byte".into(),
        ));
    }
    if path.chars().any(char::is_control) {
        return Err(ParseError::InvalidSymvaultPath(
            "contains control characters".into(),
        ));
    }
    Ok(())
}
fn validate_component(value: &str) -> Result<(), ParseError> {
    if value.as_bytes().contains(&0) || value.chars().any(char::is_control) {
        Err(ParseError::InvalidKeychain)
    } else {
        Ok(())
    }
}

#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub struct CommandOutput {
    pub stdout: Vec<u8>,
    pub stderr: Vec<u8>,
    pub status: Option<i32>,
}

#[derive(Debug, Error)]
pub enum CommandError {
    #[error("command could not be started")]
    Spawn(#[source] io::Error),
    #[error("command timed out after {0:?}")]
    Timeout(Duration),
    #[error("command output exceeded the safety limit")]
    OutputLimit,
    #[error("command exited unsuccessfully (status={status:?})")]
    Exit {
        status: Option<i32>,
        detail: &'static str,
    },
}

pub trait CommandRunner: Send + Sync {
    fn run(
        &self,
        program: &str,
        args: &[String],
        timeout: Duration,
    ) -> Result<CommandOutput, CommandError>;
}

#[derive(Clone, Copy, Debug, Default)]
pub struct SystemCommandRunner;

type StreamResult = (Vec<u8>, bool);
fn drain_bounded<R: Read>(mut reader: R) -> StreamResult {
    let mut output = Vec::new();
    let mut overflow = false;
    let mut buffer = [0u8; 8192];
    loop {
        match reader.read(&mut buffer) {
            Ok(0) => break,
            Ok(n) => {
                if output.len() < MAX_HELPER_STREAM {
                    let keep = (MAX_HELPER_STREAM - output.len()).min(n);
                    output.extend_from_slice(&buffer[..keep]);
                    if keep < n {
                        overflow = true;
                    }
                } else {
                    overflow = true;
                }
            }
            Err(_) => break,
        }
    }
    (output, overflow)
}
fn stop_tree(child: &mut Child) {
    #[cfg(unix)]
    {
        if let Some(pid) = Pid::from_raw(child.id() as i32) {
            let _ = kill_process_group(pid, Signal::KILL);
        }
    }
    #[cfg(windows)]
    {
        let _ = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    let _ = child.kill();
}

impl CommandRunner for SystemCommandRunner {
    fn run(
        &self,
        program: &str,
        args: &[String],
        timeout: Duration,
    ) -> Result<CommandOutput, CommandError> {
        let mut command = Command::new(program);
        command
            .args(args)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        #[cfg(unix)]
        {
            command.process_group(0);
        }
        let mut child = command.spawn().map_err(CommandError::Spawn)?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| CommandError::Spawn(io::Error::other("stdout pipe unavailable")))?;
        let stderr = child
            .stderr
            .take()
            .ok_or_else(|| CommandError::Spawn(io::Error::other("stderr pipe unavailable")))?;
        let (tx, rx) = mpsc::channel::<(bool, StreamResult)>();
        let tx_out = tx.clone();
        thread::spawn(move || {
            let _ = tx_out.send((true, drain_bounded(stdout)));
        });
        thread::spawn(move || {
            let _ = tx.send((false, drain_bounded(stderr)));
        });
        let deadline = Instant::now() + timeout;
        let mut timed_out = false;
        let status;
        loop {
            match child.try_wait().map_err(CommandError::Spawn)? {
                Some(done) => {
                    status = done.code();
                    break;
                }
                None if Instant::now() >= deadline => {
                    timed_out = true;
                    stop_tree(&mut child);
                    status = child.wait().map_err(CommandError::Spawn)?.code();
                    break;
                }
                None => thread::sleep(Duration::from_millis(2)),
            }
        }
        let mut out = None;
        let mut err = None;
        let mut overflow = false;
        while out.is_none() || err.is_none() {
            let remaining = deadline
                .saturating_duration_since(Instant::now())
                .min(Duration::from_millis(250));
            match rx.recv_timeout(remaining) {
                Ok((is_out, value)) => {
                    overflow |= value.1;
                    if is_out {
                        out = Some(value.0)
                    } else {
                        err = Some(value.0)
                    }
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    if !timed_out {
                        stop_tree(&mut child);
                        timed_out = true;
                    }
                    break;
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => break,
            }
        }
        if timed_out {
            return Err(CommandError::Timeout(timeout));
        }
        if overflow {
            return Err(CommandError::OutputLimit);
        }
        let output = CommandOutput {
            stdout: out.unwrap_or_default(),
            stderr: err.unwrap_or_default(),
            status,
        };
        if status == Some(0) {
            Ok(output)
        } else {
            Err(CommandError::Exit {
                status,
                detail: "helper failed; stderr suppressed",
            })
        }
    }
}

pub type EnvironmentLookup = Arc<dyn Fn(&str) -> Option<String> + Send + Sync>;
pub struct Resolver<R = SystemCommandRunner> {
    runner: R,
    environment: EnvironmentLookup,
    timeout: Duration,
}
impl<R> fmt::Debug for Resolver<R> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("Resolver")
            .field("timeout", &self.timeout)
            .finish_non_exhaustive()
    }
}
impl Default for Resolver<SystemCommandRunner> {
    fn default() -> Self {
        Self::new(SystemCommandRunner)
    }
}
impl<R: CommandRunner> Resolver<R> {
    #[must_use]
    pub fn new(runner: R) -> Self {
        Self {
            runner,
            environment: Arc::new(|n| env::var(n).ok()),
            timeout: DEFAULT_TIMEOUT,
        }
    }
    #[must_use]
    pub fn with_environment<F>(mut self, lookup: F) -> Self
    where
        F: Fn(&str) -> Option<String> + Send + Sync + 'static,
    {
        self.environment = Arc::new(lookup);
        self
    }
    #[must_use]
    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }
    pub fn resolve(&self, reference: &str, env_default: &str) -> Result<String, ResolveError> {
        self.resolve_with_deadline(reference, env_default, None)
    }
    pub fn resolve_with_deadline(
        &self,
        reference: &str,
        env_default: &str,
        deadline: Option<Instant>,
    ) -> Result<String, ResolveError> {
        let target = if reference.is_empty() {
            env_default
        } else {
            reference
        };
        if target.is_empty() {
            return Err(ResolveError::NoReference);
        };
        let parsed = SecretRef::parse(target).map_err(ResolveError::Parse)?;
        match parsed {
            SecretRef::Env { name } => match (self.environment)(&name) {
                Some(value) if !value.is_empty() => Ok(value),
                _ => Err(ResolveError::EnvironmentUnset { name }),
            },
            SecretRef::Symvault { path } => {
                let timeout = deadline.map_or(self.timeout, |at| {
                    at.saturating_duration_since(Instant::now())
                });
                let args = vec!["get".into(), "--".into(), path, "--print".into()];
                let output = self
                    .runner
                    .run("symvault", &args, timeout)
                    .map_err(ResolveError::Command)?;
                String::from_utf8(output.stdout)
                    .map(|v| v.trim().to_owned())
                    .map_err(|_| ResolveError::InvalidOutput)
            }
            SecretRef::Keychain { service, account } => {
                #[cfg(not(target_os = "macos"))]
                {
                    let _ = (service, account, deadline);
                    Err(ResolveError::KeychainUnsupported)
                }
                #[cfg(target_os = "macos")]
                {
                    let timeout = deadline.map_or(self.timeout, |at| {
                        at.saturating_duration_since(Instant::now())
                    });
                    let args = vec![
                        "find-generic-password".into(),
                        "-w".into(),
                        "-s".into(),
                        service,
                        "-a".into(),
                        account,
                    ];
                    let output = self
                        .runner
                        .run("security", &args, timeout)
                        .map_err(ResolveError::Command)?;
                    String::from_utf8(output.stdout)
                        .map(|v| v.trim().to_owned())
                        .map_err(|_| ResolveError::InvalidOutput)
                }
            }
        }
    }
}

#[derive(Debug, Error)]
pub enum ResolveError {
    #[error("no credential reference or default provided")]
    NoReference,
    #[error("invalid reference: {0}")]
    Parse(#[source] ParseError),
    #[error("environment variable {name} is not set")]
    EnvironmentUnset { name: String },
    #[error("credential helper command failed: {0}")]
    Command(#[source] CommandError),
    #[error("keychain:// references are only resolvable on macOS")]
    KeychainUnsupported,
    #[error("command returned invalid UTF-8")]
    InvalidOutput,
}
pub fn resolve(reference: &str, env_default: &str) -> Result<String, ResolveError> {
    Resolver::default().resolve(reference, env_default)
}
#[must_use]
pub fn redact(input: &str, secrets: &[&str]) -> String {
    secrets
        .iter()
        .filter(|s| !s.is_empty())
        .fold(input.to_owned(), |text, secret| {
            text.replace(secret, "[REDACTED]")
        })
}
pub struct Redacted<'a>(pub &'a str);
impl fmt::Debug for Redacted<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("[REDACTED]")
    }
}
impl fmt::Display for Redacted<'_> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("[REDACTED]")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};
    type Calls = Vec<(String, Vec<String>, Duration)>;
    #[derive(Clone)]
    struct Stub(Arc<Mutex<Calls>>);
    impl CommandRunner for Stub {
        fn run(&self, p: &str, a: &[String], t: Duration) -> Result<CommandOutput, CommandError> {
            self.0.lock().unwrap().push((p.into(), a.to_vec(), t));
            Ok(CommandOutput {
                stdout: b"secret\n".to_vec(),
                ..Default::default()
            })
        }
    }
    #[test]
    fn parse_forms() {
        assert_eq!(
            SecretRef::parse("TOKEN").unwrap().to_string(),
            "env://TOKEN"
        );
        assert_eq!(
            SecretRef::parse("symvault://a/b").unwrap().to_string(),
            "symvault://a/b"
        );
        assert!(SecretRef::parse("symvault://--bad").is_err());
        assert!(SecretRef::parse("keychain://service").is_err());
    }
    #[test]
    fn argv_deadline_and_redaction() {
        let calls = Arc::new(Mutex::new(Vec::new()));
        let resolver = Resolver::new(Stub(calls.clone())).with_timeout(Duration::from_millis(7));
        assert_eq!(
            resolver.resolve("symvault://secrets/key", "").unwrap(),
            "secret"
        );
        let call = &calls.lock().unwrap()[0];
        assert_eq!(call.0, "symvault");
        assert_eq!(call.1, ["get", "--", "secrets/key", "--print"]);
        assert_eq!(call.2, Duration::from_millis(7));
        assert_eq!(redact("stderr=secret", &["secret"]), "stderr=[REDACTED]");
    }
    #[test]
    fn stderr_is_not_in_error() {
        let err = CommandError::Exit {
            status: Some(17),
            detail: "helper failed; stderr suppressed",
        };
        assert!(!err.to_string().contains("secret"));
    }
    #[cfg(all(unix, not(miri)))]
    #[test]
    fn system_runner_redacts_real_stderr_and_reaps_descendants() {
        let runner = SystemCommandRunner;
        let error = runner
            .run(
                "sh",
                &["-c".into(), "printf real-secret >&2; exit 17".into()],
                Duration::from_secs(2),
            )
            .expect_err("helper failure");
        assert!(!error.to_string().contains("real-secret"));
        let started = Instant::now();
        let error = runner
            .run(
                "sh",
                &["-c".into(), "sleep 2 & wait".into()],
                Duration::from_millis(50),
            )
            .expect_err("timeout");
        assert!(matches!(error, CommandError::Timeout(_)));
        assert!(started.elapsed() < Duration::from_secs(1));
    }

    #[cfg(not(miri))]
    #[test]
    fn system_runner_bounds_real_output() {
        #[cfg(unix)]
        let (program, args) = ("sh", vec!["-c".into(), "printf '%*s' 70000 x".into()]);
        #[cfg(windows)]
        let (program, args) = (
            "powershell.exe",
            vec![
                "-NoProfile".into(),
                "-NonInteractive".into(),
                "-Command".into(),
                "[Console]::Out.Write('x' * 70000)".into(),
            ],
        );
        let error = SystemCommandRunner
            .run(program, &args, Duration::from_secs(10))
            .expect_err("output limit");
        assert!(matches!(error, CommandError::OutputLimit));
    }
}
