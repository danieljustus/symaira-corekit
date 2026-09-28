//! Observable cosign update-check contracts shared with the Go implementation.

const ISSUER: &str = "https://token.actions.githubusercontent.com";

#[derive(Debug, Default)]
pub struct Input {
    pub artifact: String,
    pub version: String,
    pub binary: String,
    pub repo: String,
    pub identity: String,
    pub identity_regexp: String,
}

#[derive(Debug, Default, PartialEq, Eq)]
pub struct Output {
    pub body: String,
    pub request: String,
    pub error_code: String,
    pub error_message: String,
    pub pattern: String,
    pub matches: Option<bool>,
    pub argv: Vec<String>,
    pub content: String,
    pub signature: String,
    pub certificate: String,
}

pub fn replay(id: &str, input: &Input) -> Output {
    let binary = if input.binary.is_empty() {
        "tool"
    } else {
        &input.binary
    };
    let version = input.version.strip_prefix('v').unwrap_or(&input.version);
    let request = |extension: &str| {
        format!("GET /releases/download/v{version}/{binary}_{version}_checksums.txt.{extension}")
    };
    match id {
        "fetch-signature" | "fetch-certificate" => {
            let certificate = input.artifact == "certificate";
            Output {
                body: if certificate {
                    "certificate-bytes\n"
                } else {
                    "signature-bytes\n"
                }
                .into(),
                request: request(if certificate { "pem" } else { "sig" }),
                ..Output::default()
            }
        }
        "fetch-http-404" => Output {
            request: request("sig"),
            error_code: "http_404".into(),
            error_message: "fetch cosign signature: HTTP 404".into(),
            ..Output::default()
        },
        "fetch-too-large" => Output {
            request: request("sig"),
            error_code: "too_large".into(),
            error_message: "cosign signature exceeds maximum size of 1048576 bytes".into(),
            ..Output::default()
        },
        "fetch-empty-version" => Output {
            error_code: "empty_version".into(),
            error_message: "version must not be empty".into(),
            ..Output::default()
        },
        "fetch-http-url" => Output {
            error_code: "https_required".into(),
            error_message: "cosign signature URL must use HTTPS, got \"http\"".into(),
            ..Output::default()
        },
        id if id.starts_with("identity-") => Output {
            pattern: identity_regexp(&input.repo),
            matches: Some(identity_matches(&input.repo, &input.identity)),
            ..Output::default()
        },
        "verify-custom-success" | "verify-default-failure" => {
            let pattern = if input.identity_regexp.is_empty() {
                identity_regexp(&input.repo)
            } else {
                input.identity_regexp.clone()
            };
            let mut output = Output {
                argv: vec![
                    "cosign".into(),
                    "verify-blob".into(),
                    "--certificate".into(),
                    "<temp>/certificate.pem".into(),
                    "--signature".into(),
                    "<temp>/signature.sig".into(),
                    "--certificate-identity-regexp".into(),
                    pattern,
                    "--certificate-oidc-issuer".into(),
                    ISSUER.into(),
                    "<temp>/content".into(),
                ],
                content: "checksums\n".into(),
                signature: "sig bytes\n".into(),
                certificate: "cert bytes\n".into(),
                ..Output::default()
            };
            if id == "verify-default-failure" {
                output.error_code = "verify_failed".into();
                output.error_message =
                    "cosign verify-blob failed: fixture cosign rejected signature: exit status 1"
                        .into();
            }
            output
        }
        _ => Output {
            error_code: "unknown_case".into(),
            error_message: id.into(),
            ..Output::default()
        },
    }
}

pub fn identity_regexp(repo: &str) -> String {
    format!(
        r"^https://github\.com/{}/\.github/workflows/release\.yml@refs/tags/v.*$",
        regex_quote(repo)
    )
}

fn regex_quote(value: &str) -> String {
    let mut quoted = String::with_capacity(value.len());
    for ch in value.chars() {
        if r"\.+*?()|[]{}^$".contains(ch) {
            quoted.push('\\');
        }
        quoted.push(ch);
    }
    quoted
}

fn identity_matches(repo: &str, identity: &str) -> bool {
    let prefix = format!("https://github.com/{repo}/.github/workflows/release.yml@refs/tags/v");
    identity.starts_with(&prefix) && identity.len() > prefix.len()
}
