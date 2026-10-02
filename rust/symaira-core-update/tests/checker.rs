#[path = "common/static_update.rs"]
mod static_update;

use symaira_core_update::Checker;

#[test]
fn invalid_current_never_calls_transport() {
    let mut checker = Checker::new("owner", "repo");
    checker.transport = Some(Box::new(|_, _| {
        panic!("ineligible current must not request")
    }));
    for current in ["dev", "1.2.3-beta", "", "1.2"] {
        assert_eq!(checker.check_with_force(current, true).unwrap(), None);
    }
}

use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    io::{Read, Write},
    net::TcpListener,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
    sync::{Arc, Mutex},
    time::Duration,
};
use symaira_core_update::{Release, request};

// A separate process isolates HOME/XDG without unsafe process-global env writes.
// Every corpus replay owns its cache, including parallel cargo/nextest executions.
fn isolated(name: &str) -> bool {
    if std::env::var("SYMAIRA_CHECKER_CHILD").as_deref() == Ok(name) {
        return false;
    }
    static NONCE: AtomicU64 = AtomicU64::new(0);
    let root = loop {
        let path = std::env::temp_dir().join(format!(
            "checker-{}-{}-{}",
            std::process::id(),
            name,
            NONCE.fetch_add(1, Ordering::Relaxed)
        ));
        match std::fs::create_dir(&path) {
            Ok(()) => break path,
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => panic!("create private checker root: {error}"),
        }
    };
    struct OwnedRoot(PathBuf);
    impl Drop for OwnedRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }
    let owned = OwnedRoot(root);
    for directory in ["home", "cache", "tmp"] {
        std::fs::create_dir(owned.0.join(directory)).unwrap();
    }
    let xdg = std::env::var_os("XDG_CACHE_HOME").filter(|path| {
        name == "default_path_matches_go_home_fallback" && !PathBuf::from(path).is_absolute()
    });
    let output = Command::new(std::env::current_exe().unwrap())
        .args([name, "--exact", "--nocapture"])
        .env("SYMAIRA_CHECKER_CHILD", name)
        .env("HOME", owned.0.join("home"))
        .env("USERPROFILE", owned.0.join("home"))
        .env(
            "XDG_CACHE_HOME",
            xdg.unwrap_or_else(|| owned.0.join("cache").into_os_string()),
        )
        .env("TMPDIR", owned.0.join("tmp"))
        .env("TMP", owned.0.join("tmp"))
        .env("TEMP", owned.0.join("tmp"))
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "isolated {name} failed:\n{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    true
}

#[derive(Deserialize)]
struct Fixture {
    observations: Observations,
}
#[derive(Deserialize)]
struct Observations {
    cases: Vec<Case>,
    default_path: String,
    canonical_url: String,
    relative_xdg_path: String,
    empty_xdg_path: String,
}
#[derive(Deserialize)]
struct Case {
    id: String,
    mode: String,
    custom_endpoint: bool,
    replies: Vec<Reply>,
    steps: Vec<Step>,
    results: Vec<Value>,
}
#[derive(Clone, Deserialize)]
struct Reply {
    body: String,
    status: u16,
    rate_limit: bool,
    error: String,
}
#[derive(Deserialize)]
struct Step {
    endpoint_override: bool,
    current: String,
    force: bool,
    fresh: bool,
    expire: bool,
}

fn release_json(release: Release) -> Value {
    json!({"TagName": release.tag_name, "Body": release.body, "HTMLURL": release.html_url,
        "Assets": release.assets.into_iter().map(|a| json!({"Name":a.name,"BrowserDownloadURL":a.browser_download_url,"Size":a.size})).collect::<Vec<_>>()})
}

// Bind before spawning: readiness is the listener, never a timing sleep.
fn loopback(reply: Reply, current: &str) -> (Result<request::Response, request::Error>, String) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let handle = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut headers = Vec::new();
        let mut byte = [0];
        while !headers.ends_with(b"\r\n\r\n") {
            stream.read_exact(&mut byte).unwrap();
            headers.push(byte[0]);
        }
        let headers = String::from_utf8(headers).unwrap();
        let field = |name: &str| {
            headers
                .lines()
                .filter_map(|line| line.split_once(':'))
                .find(|(key, _)| key.eq_ignore_ascii_case(name))
                .unwrap()
                .1
                .trim()
                .to_owned()
        };
        assert_eq!(field("Accept"), "application/vnd.github+json");
        let agent = field("User-Agent");
        write!(
            stream,
            "HTTP/1.1 {} Test\r\nContent-Length: {}\r\nConnection: close\r\n{}\r\n{}",
            reply.status,
            reply.body.len(),
            if reply.rate_limit {
                "X-RateLimit-Remaining: 0\r\n"
            } else {
                ""
            },
            reply.body
        )
        .unwrap();
        agent
    });
    let result = request::fetch(
        &format!("http://{address}/latest"),
        current,
        Duration::from_secs(3),
    );
    (result, handle.join().unwrap())
}

#[test]
fn public_checker_corpus_matches_go() {
    if isolated("public_checker_corpus_matches_go") {
        return;
    }
    replay_corpus(true);
}

#[test]
fn public_checker_injected_corpus_matches_go() {
    if isolated("public_checker_injected_corpus_matches_go") {
        return;
    }
    replay_corpus(false);
}

fn replay_corpus(real_http: bool) {
    let path = std::env::var_os("UPDATE_CHECKER_FIXTURE")
        .map(PathBuf::from)
        .unwrap_or_else(|| static_update::fixture_path("checker"));
    let fixture: Fixture = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let observations = fixture.observations;
    assert_eq!(observations.cases.len(), 21, "nonzero complete corpus");
    let root = PathBuf::from(std::env::var_os("XDG_CACHE_HOME").expect("harness disposable XDG"));
    assert!(root.is_absolute());
    assert_eq!(
        symaira_core_update::default_cache_path("../owner", "repo/../../x")
            .strip_prefix(&root)
            .unwrap()
            .to_string_lossy()
            .replace('\\', "/"),
        observations.default_path
    );
    assert_eq!(
        Checker::new("owner", "repo").latest_release_url,
        observations.canonical_url
    );
    // HOME fallback is verified in separate harness processes, avoiding global env mutation.
    assert_eq!(
        observations.relative_xdg_path,
        format!(".cache/{}", observations.default_path)
    );
    assert_eq!(observations.empty_xdg_path, observations.relative_xdg_path);
    for case in observations.cases {
        let state = Arc::new(Mutex::new((0usize, Vec::<String>::new())));
        let replies = Arc::new(case.replies);
        let owner = format!("owner-{}", case.id);
        let new_checker = || {
            let mut checker = Checker::new(&owner, "repo");
            if case.custom_endpoint {
                checker.latest_release_url = "https://example.invalid/latest".into();
            }
            match case.mode.as_str() {
                "empty" => checker.cache_path = PathBuf::new(),
                "explicit" => checker.cache_path = root.join(&case.id).join("response.json"),
                "default" => {}
                _ => panic!("unknown persistence mode"),
            }
            let state = Arc::clone(&state);
            let replies = Arc::clone(&replies);
            let expected_url = checker.latest_release_url.clone();
            let allow_override = case.id == "endpoint-isolation";
            checker.transport = Some(Box::new(move |url, current| {
                assert!(
                    url == expected_url
                        || (allow_override && url == "https://example.invalid/latest")
                );
                let mut state = state.lock().unwrap();
                let reply = replies
                    .get(state.0)
                    .expect("no unexpected HTTP request")
                    .clone();
                state.0 += 1;
                if !reply.error.is_empty() {
                    state
                        .1
                        .push(format!("symaira-updatecheck/{}", current.trim()));
                    return Err(request::Error {
                        code: "network",
                        message: format!("request latest release: {}", reply.error),
                    });
                }
                if real_http {
                    let (response, agent) = loopback(reply, current);
                    state.1.push(agent);
                    response
                } else {
                    state
                        .1
                        .push(format!("symaira-updatecheck/{}", current.trim()));
                    if reply.rate_limit {
                        Err(request::Error {
                            code: "rate_limit",
                            message: "GitHub API rate limit exceeded".into(),
                        })
                    } else {
                        Ok(request::Response {
                            status: reply.status,
                            body: reply.body.into_bytes(),
                        })
                    }
                }
            }));
            checker
        };
        let mut checker = new_checker();
        assert_eq!(case.steps.len(), case.results.len());
        assert!(!case.steps.is_empty());
        for (step, expected) in case.steps.into_iter().zip(case.results) {
            if step.fresh {
                checker = new_checker();
            }
            if step.endpoint_override {
                checker.latest_release_url = "https://example.invalid/latest".into();
            }
            if step.expire {
                checker.cache_ttl = Duration::ZERO;
            }
            let (release, error) = match checker.check_with_force(&step.current, step.force) {
                Ok(release) => (release.map(release_json), None),
                Err(error) => (None, Some(error)),
            };
            let state = state.lock().unwrap();
            let actual = json!({"release":release,"error":error,"calls":state.0,"user_agents":state.1,"cache_exists":checker.cache_path.is_file()});
            assert_eq!(
                actual, expected,
                "scenario {} current {}",
                case.id, step.current
            );
        }
    }
}

#[test]
fn default_transport_composes_request_and_checker() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let server = std::thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        let mut headers = Vec::new();
        let mut byte = [0];
        while !headers.ends_with(b"\r\n\r\n") {
            stream.read_exact(&mut byte).unwrap();
            headers.push(byte[0]);
        }
        assert!(
            String::from_utf8(headers)
                .unwrap()
                .contains("symaira-updatecheck/v1.0.0")
        );
        let body = r#"{"tag_name":"v1.1.0"}"#;
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
            body.len(),
            body
        )
        .unwrap();
    });
    let mut checker = Checker::new("owner", "repo");
    checker.latest_release_url = format!("http://{address}/");
    checker.cache_path = PathBuf::new();
    assert_eq!(
        checker.check(" v1.0.0 ").unwrap().unwrap().tag_name,
        "v1.1.0"
    );
    server.join().unwrap();
}

#[test]
fn default_path_matches_go_home_fallback() {
    if isolated("default_path_matches_go_home_fallback") {
        return;
    }
    let fixture: Fixture = serde_json::from_str(
        &std::fs::read_to_string(static_update::fixture_path("checker")).unwrap(),
    )
    .unwrap();
    let cache = PathBuf::from(std::env::var_os("XDG_CACHE_HOME").unwrap());
    let expected = if cache.is_absolute() {
        cache.join(fixture.observations.default_path)
    } else {
        PathBuf::from(std::env::var_os("HOME").unwrap())
            .join(fixture.observations.relative_xdg_path)
    };
    assert_eq!(
        symaira_core_update::default_cache_path("../owner", "repo/../../x"),
        expected
    );
}
