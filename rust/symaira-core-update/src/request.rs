//! Update-release HTTP request behavior shared with the Go checker.

use reqwest::blocking::{Client, ClientBuilder};
use reqwest::redirect::Policy;
use reqwest::tls::Version;
use std::error::Error as _;
use std::io::{self, Read};
use std::time::Duration;

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
    let client = secure_client_builder(timeout)
        .build()
        .map_err(classify_network)?;
    fetch_with_client(&client, url, current_version)
}

pub(crate) fn secure_client_builder(timeout: Duration) -> ClientBuilder {
    let mut builder = Client::builder()
        .redirect(Policy::none())
        .tls_version_min(Version::TLS_1_3);
    if !timeout.is_zero() {
        builder = builder.timeout(timeout);
    }
    builder
}

pub(crate) fn secure_download_client_builder(timeout: Duration) -> ClientBuilder {
    secure_client_builder(timeout).redirect(Policy::custom(|attempt| {
        let host = attempt.url().host_str().unwrap_or_default().to_owned();
        let scheme = attempt.url().scheme().to_owned();
        if scheme != "https" {
            attempt.error(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!("refusing redirect to non-HTTPS scheme {scheme:?}"),
            ))
        } else if !is_github_host(&host) {
            attempt.error(io::Error::new(
                io::ErrorKind::PermissionDenied,
                format!("refusing redirect to non-GitHub host {host:?}"),
            ))
        } else if attempt.previous().len() >= 10 {
            attempt.error(io::Error::other("stopped after 10 redirects"))
        } else {
            attempt.follow()
        }
    }))
}

fn fetch_with_client(client: &Client, url: &str, current_version: &str) -> Result<Response, Error> {
    let mut target = url.trim().to_owned();
    for redirects in 0..=10 {
        let result = client
            .get(&target)
            .header("Accept", "application/vnd.github+json")
            .header("Accept-Encoding", "gzip")
            .header(
                "User-Agent",
                &format!("symaira-updatecheck/{}", current_version.trim()),
            )
            .send();
        let mut response = match result {
            Ok(response) => response,
            Err(error) => return Err(classify_network(error)),
        };
        let status = response.status().as_u16();
        if (300..400).contains(&status) {
            let next = response
                .headers()
                .get(reqwest::header::LOCATION)
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
            if target_next.scheme() != "https" {
                return Err(Error {
                    code: "network",
                    message: format!(
                        "request latest release: refusing redirect to non-HTTPS scheme {:?}",
                        target_next.scheme()
                    ),
                });
            }
            let host = target_next.host_str().unwrap_or_default();
            if !is_github_host(host) {
                return Err(Error {
                    code: "network",
                    message: format!(
                        "request latest release: refusing redirect to non-GitHub host {host:?}"
                    ),
                });
            }
            target = target_next.to_string();
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
        (&mut response)
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

fn resolve_redirect(base: &str, next: &str) -> Option<reqwest::Url> {
    reqwest::Url::parse(base).ok()?.join(next).ok()
}

fn classify_network(error: reqwest::Error) -> Error {
    let mut details = format!("{error:?}").to_ascii_lowercase();
    let mut source = error.source();
    let mut refused = false;
    while let Some(cause) = source {
        details.push_str(&cause.to_string().to_ascii_lowercase());
        refused |= cause
            .downcast_ref::<io::Error>()
            .is_some_and(|io| io.kind() == io::ErrorKind::ConnectionRefused);
        source = cause.source();
    }
    let code = if error.is_timeout() {
        "timeout"
    } else if details.contains("certificate") || details.contains("unknownissuer") {
        "tls_certificate"
    } else if refused || details.contains("connection refused") {
        "connection_refused"
    } else {
        "network"
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
    use super::{
        fetch, fetch_with_client, is_github_host, resolve_redirect, secure_client_builder,
    };
    use reqwest::tls::{Certificate, Version};
    use std::time::Duration;

    #[test]
    fn redirect_location_uses_url_semantics_before_host_check() {
        let base = "https://api.github.com/repos/org/repo/releases/latest";
        let foreign = resolve_redirect(base, "//evil.example/steal").unwrap();
        assert_eq!(foreign.as_str(), "https://evil.example/steal");
        assert!(!is_github_host(foreign.host_str().unwrap()));
        assert_eq!(
            resolve_redirect(base, "../tags?per_page=1")
                .unwrap()
                .as_str(),
            "https://api.github.com/repos/org/repo/tags?per_page=1"
        );
    }

    #[test]
    fn refused_connection_has_go_request_classification() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let addr = listener.local_addr().unwrap();
        drop(listener);
        // Windows can take longer than two seconds to report the refused
        // connect. Do not let the test's deadline replace that native error.
        let actual =
            fetch(&format!("http://{addr}/"), "1.0.0", Duration::from_secs(30)).unwrap_err();
        assert_eq!(actual.code, "connection_refused");
        assert_eq!(actual.message, "request latest release");
    }

    #[test]
    #[ignore = "requires the Go TLS 1.2 and 1.3 fixture servers"]
    fn tls_protocol_minimum_rejects_1_2() {
        fn trusted_client(cert_path: &str, minimum: Option<Version>) -> reqwest::blocking::Client {
            let certificate = Certificate::from_der(&std::fs::read(cert_path).unwrap()).unwrap();
            let mut builder =
                secure_client_builder(Duration::from_secs(2)).tls_certs_only([certificate]);
            if let Some(version) = minimum {
                builder = builder.tls_version_min(version);
            }
            builder.build().unwrap()
        }

        let tls12_url = std::env::var("UPDATE_REQUEST_TLS12_URL").unwrap();
        let tls12_cert = std::env::var("UPDATE_REQUEST_TLS12_CERT").unwrap();
        let tls13_url = std::env::var("UPDATE_REQUEST_TLS13_URL").unwrap();
        let tls13_cert = std::env::var("UPDATE_REQUEST_TLS13_CERT").unwrap();
        let tls12 = trusted_client(&tls12_cert, None);
        assert!(
            fetch_with_client(&tls12, &tls12_url, "1.2.3").is_err(),
            "TLS 1.2-only peer must not negotiate with the production client"
        );
        let weak_control = trusted_client(&tls12_cert, Some(Version::TLS_1_2));
        assert_eq!(
            fetch_with_client(&weak_control, &tls12_url, "1.2.3")
                .expect("control proves the TLS 1.2 server and certificate work")
                .status,
            200
        );
        let tls13 = trusted_client(&tls13_cert, None);
        assert_eq!(
            fetch_with_client(&tls13, &tls13_url, "1.2.3")
                .expect("TLS 1.3 with a trusted certificate must work")
                .status,
            200
        );
        let foreign =
            fetch_with_client(&tls13, &format!("{tls13_url}/_foreign_"), "1.2.3").unwrap_err();
        assert!(
            foreign
                .message
                .contains("refusing redirect to non-GitHub host")
        );
        let downgrade =
            fetch_with_client(&tls13, &format!("{tls13_url}/_downgrade_"), "1.2.3").unwrap_err();
        assert!(
            downgrade
                .message
                .contains("refusing redirect to non-HTTPS scheme")
        );
    }
}
