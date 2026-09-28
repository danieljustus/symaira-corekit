//! Update-release HTTP request behavior shared with the Go checker.

use std::io::Read;
use std::time::Duration;
use ureq::{Agent, tls::TlsConfig};

const MAX_RESPONSE: u64 = 1 << 20;

#[derive(Debug, PartialEq, Eq)]
pub struct Error {
    pub code: &'static str,
    pub message: String,
}

#[derive(Debug, PartialEq, Eq)]
pub struct Response {
    pub status: u16,
    pub body: Vec<u8>,
}

/// Fetches a latest-release response from an explicit URL.
pub fn fetch(url: &str, current_version: &str, timeout: Duration) -> Result<Response, Error> {
    let mut config = Agent::config_builder()
        .http_status_as_error(false)
        .max_redirects(0)
        .timeout_global((!timeout.is_zero()).then_some(timeout));
    // ureq exposes certificate roots but not a TLS minimum-version setting.
    config = config.tls_config(TlsConfig::builder().build());
    let agent: Agent = config.build().into();
    let mut target = url.trim().to_owned();
    for redirects in 0..=10 {
        let result = agent
            .get(&target)
            .header("Accept", "application/vnd.github+json")
            .header("Accept-Encoding", "gzip")
            .header(
                "User-Agent",
                &format!("symaira-updatecheck/{}", current_version.trim()),
            )
            .call();
        let mut response = match result {
            Ok(response) => response,
            Err(error) => return Err(classify_network(error)),
        };
        let status = response.status().as_u16();
        if (300..400).contains(&status) {
            let next = response
                .headers()
                .get("location")
                .and_then(|value| value.to_str().ok())
                .ok_or_else(|| Error {
                    code: "redirect",
                    message: format!("GitHub API returned HTTP {status}"),
                })?;
            if redirects == 10 {
                return Err(Error {
                    code: "redirect_cap",
                    message: "stopped after 10 redirects".into(),
                });
            }
            let target_next = resolve_redirect(&target, next).ok_or_else(|| Error {
                code: "redirect",
                message: format!("invalid redirect URL {next:?}"),
            })?;
            let host = url_host(&target_next).unwrap_or_default();
            if !is_github_host(host) {
                return Err(Error {
                    code: "redirect",
                    message: format!("refusing redirect to non-GitHub host {host:?}"),
                });
            }
            target = target_next;
            continue;
        }
        if status != 200 {
            return Err(Error {
                code: if status == 404 {
                    "http_404"
                } else if status == 429 {
                    "http_429"
                } else {
                    "http_status"
                },
                message: format!("GitHub API returned HTTP {status}"),
            });
        }
        let mut body = Vec::new();
        response
            .body_mut()
            .as_reader()
            .take(MAX_RESPONSE)
            .read_to_end(&mut body)
            .map_err(|error| Error {
                code: "decode",
                message: format!("decode latest release response: {error}"),
            })?;
        return Ok(Response { status, body });
    }
    unreachable!("redirect loop always returns")
}

/// Matches the Go secure client's accepted GitHub redirect hosts.
#[must_use]
pub fn is_github_host(host: &str) -> bool {
    let host = host.split(':').next().unwrap_or(host).to_ascii_lowercase();
    host == "github.com"
        || host == "api.github.com"
        || host.ends_with(".github.com")
        || host.ends_with(".githubusercontent.com")
}

fn resolve_redirect(base: &str, next: &str) -> Option<String> {
    if next.contains("://") {
        return Some(next.to_owned());
    }
    let scheme_end = base.find("://")? + 3;
    let origin_end = base[scheme_end..]
        .find('/')
        .map_or(base.len(), |index| scheme_end + index);
    let origin = &base[..origin_end];
    if next.starts_with('/') {
        Some(format!("{origin}{next}"))
    } else {
        let path_end = base.rfind('/')?;
        Some(format!("{}/{next}", &base[..path_end]))
    }
}

fn url_host(url: &str) -> Option<&str> {
    url.split_once("://")?
        .1
        .split('/')
        .next()?
        .split('@')
        .next_back()
}

fn classify_network(error: ureq::Error) -> Error {
    let detail = format!("{error:?}").to_ascii_lowercase();
    let code = match &error {
        ureq::Error::Timeout(_) => "timeout",
        ureq::Error::Tls(_) | ureq::Error::Rustls(_) => "tls_certificate",
        _ if detail.contains("certificate") || detail.contains("unknownissuer") => {
            "tls_certificate"
        }
        ureq::Error::Io(error) if error.kind() == std::io::ErrorKind::ConnectionRefused => {
            "connection_refused"
        }
        _ => "network",
    };
    Error {
        code,
        message: if code == "timeout" || code == "connection_refused" || code == "tls_certificate" {
            if code == "tls_certificate" {
                "update check failed: TLS certificate verification error".into()
            } else {
                "request latest release".into()
            }
        } else {
            format!("request latest release: {error}")
        },
    }
}

#[cfg(test)]
mod tests {
    use super::classify_network;
    use std::io::{Error, ErrorKind};

    #[test]
    fn refused_io_error_has_go_request_classification() {
        let actual = classify_network(ureq::Error::Io(Error::from(ErrorKind::ConnectionRefused)));
        assert_eq!(actual.code, "connection_refused");
        assert_eq!(actual.message, "request latest release");
    }
}
