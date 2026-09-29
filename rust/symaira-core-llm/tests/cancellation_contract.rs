#![deny(unsafe_code)]

use serde_json::Value;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};
use symaira_core_llm::{
    CancellationToken, ClientBuilder, ErrorCode, GenerateOption, Message, NativeChatOption, lookup,
};

#[test]
fn cancellable_context_methods_match_go_and_do_not_send_requests() {
    let fixture: Value = serde_json::from_str(include_str!(
        "../../../testdata/rust-port/fixtures/llm/go-oracle.json"
    ))
    .unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    listener.set_nonblocking(true).unwrap();
    let address = listener.local_addr().unwrap();
    let server = thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_millis(250);
        let mut accepted = 0;
        while Instant::now() < deadline {
            match listener.accept() {
                Ok(_) => accepted += 1,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(2));
                }
                Err(error) => panic!("unexpected listener error: {error}"),
            }
        }
        accepted
    });
    let base = format!("http://{address}");
    let openai = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{base}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let openrouter = ClientBuilder::new(lookup("openrouter").unwrap().clone(), "")
        .base_url(format!("{base}/api/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let ollama = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(base.clone())
        .build()
        .unwrap();
    let token = CancellationToken::new();
    token.cancel();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let mut observed = Vec::new();
    runtime.block_on(async {
        let embedding = openai
            .embed_cancellable(&token, "", &["input".into()], None)
            .await
            .unwrap_err();
        observed.push(("embed", embedding.code));

        let models = openrouter
            .list_models_cancellable(&token)
            .await
            .unwrap_err();
        observed.push(("list_models", models.code));

        let native_embedding = ollama
            .embed_native_cancellable(&token, "", &["input".into()], 2)
            .await
            .unwrap_err();
        observed.push(("embed_native", native_embedding.code));

        let native_models = ollama
            .list_ollama_models_cancellable(&token)
            .await
            .unwrap_err();
        observed.push(("list_ollama_models", native_models.code));

        let generate = ollama
            .generate_cancellable(&token, "", "prompt", &GenerateOption::default(), |_| Ok(()))
            .await
            .unwrap_err();
        observed.push(("generate", generate.code));

        let chat = ollama
            .chat_stream_cancellable(
                &token,
                "",
                &[Message {
                    role: "user".into(),
                    content: "question".into(),
                }],
                &NativeChatOption::default(),
                |_| Ok(()),
            )
            .await
            .unwrap_err();
        observed.push(("chat_stream", chat.code));

        let ping = ollama.ping_cancellable(&token).await.unwrap_err();
        observed.push(("ping", ping.code));

        // Static model listing is local in Go and must not turn an already
        // canceled context into a transport error.
        let static_models = openai.list_models_cancellable(&token).await.unwrap();
        assert_eq!(static_models[0].id, openai.descriptor().default_model());
    });

    let expected = fixture["cancellable_calls"].as_array().unwrap();
    assert_eq!(observed.len(), expected.len());
    for ((operation, code), expected) in observed.iter().zip(expected) {
        assert_eq!(*operation, expected["operation"].as_str().unwrap());
        assert_eq!(code.as_str(), expected["error_code"].as_str().unwrap());
        assert_eq!(expected["request_observed"].as_bool(), Some(false));
    }
    assert_eq!(
        server.join().unwrap(),
        0,
        "canceled call reached the server"
    );
}

#[test]
fn cancellable_guards_keep_local_errors_ahead_of_cancellation() {
    let token = CancellationToken::new();
    token.cancel();
    let non_ollama = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .api_key("dummy-key")
        .build()
        .unwrap();
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let error = runtime
        .block_on(non_ollama.embed_native_cancellable(&token, "", &["input".into()], 0))
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::ProviderError);
    assert!(
        error
            .detail
            .contains("only available for the ollama provider")
    );
}

#[test]
fn cancellation_drops_embedding_discovery_and_ollama_stream_reads() {
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
        .unwrap();

    let (url, started, server) = stalling_headers_server();
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let worker = runtime.spawn(async move {
        client
            .embed_cancellable(&worker_token, "", &["input".into()], None)
            .await
    });
    started.recv_timeout(Duration::from_secs(2)).unwrap();
    token.cancel();
    let error = runtime
        .block_on(async { tokio::time::timeout(Duration::from_secs(2), worker).await })
        .expect("canceled embedding waiting for headers did not return promptly")
        .unwrap()
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(
        server.join().unwrap(),
        "embedding request stayed open while waiting for headers"
    );

    let (url, started, server) = stalling_server(b"{");
    let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
        .base_url(format!("{url}/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let worker = runtime.spawn(async move {
        client
            .embed_cancellable(&worker_token, "", &["input".into()], None)
            .await
    });
    started.recv_timeout(Duration::from_secs(2)).unwrap();
    token.cancel();
    let error = runtime
        .block_on(async { tokio::time::timeout(Duration::from_secs(2), worker).await })
        .expect("canceled embedding did not return promptly")
        .unwrap()
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(server.join().unwrap(), "embedding connection stayed open");

    let (url, started, server) = stalling_server(b"{");
    let client = ClientBuilder::new(lookup("openrouter").unwrap().clone(), "")
        .base_url(format!("{url}/api/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let worker = runtime.spawn(async move { client.list_models_cancellable(&worker_token).await });
    started.recv_timeout(Duration::from_secs(2)).unwrap();
    token.cancel();
    let error = runtime
        .block_on(async { tokio::time::timeout(Duration::from_secs(2), worker).await })
        .expect("canceled model discovery did not return promptly")
        .unwrap()
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(
        server.join().unwrap(),
        "model discovery connection stayed open"
    );

    let first_record = b"{\"model\":\"llama3.1\",\"response\":\"piece\",\"done\":false}\n";
    let (url, started_rx, server) = stalling_server(first_record);
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let (seen_tx, seen_rx) = std::sync::mpsc::channel();
    let worker = runtime.spawn(async move {
        client
            .generate_cancellable(
                &worker_token,
                "",
                "prompt",
                &GenerateOption::default(),
                move |_| {
                    seen_tx.send(()).unwrap();
                    Ok(())
                },
            )
            .await
    });
    seen_rx
        .recv_timeout(Duration::from_secs(2))
        .expect("Ollama did not deliver its first record");
    started_rx
        .recv_timeout(Duration::from_secs(2))
        .expect("Ollama server did not finish writing its first record");
    token.cancel();
    let error = runtime
        .block_on(async { tokio::time::timeout(Duration::from_secs(2), worker).await })
        .expect("canceled Ollama stream did not return promptly")
        .unwrap()
        .unwrap_err();
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(
        error
            .detail
            .contains("stream interrupted: context canceled")
    );
    assert!(
        server.join().unwrap(),
        "Ollama stream connection stayed open"
    );
}

fn stalling_server(body: &[u8]) -> (String, std::sync::mpsc::Receiver<()>, JoinHandle<bool>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let (started_tx, started_rx) = std::sync::mpsc::channel();
    let body = body.to_vec();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        read_request(&mut stream);
        write!(
            stream,
            "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: keep-alive\r\n\r\n{:X}\r\n",
            body.len()
        )
        .unwrap();
        stream.write_all(&body).unwrap();
        stream.write_all(b"\r\n").unwrap();
        stream.flush().unwrap();
        started_tx.send(()).unwrap();
        server_observes_close(&mut stream)
    });
    (format!("http://{address}"), started_rx, server)
}

fn stalling_headers_server() -> (String, std::sync::mpsc::Receiver<()>, JoinHandle<bool>) {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let address = listener.local_addr().unwrap();
    let (started_tx, started_rx) = std::sync::mpsc::channel();
    let server = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        read_request(&mut stream);
        started_tx.send(()).unwrap();
        server_observes_close(&mut stream)
    });
    (format!("http://{address}"), started_rx, server)
}

fn read_request(stream: &mut TcpStream) {
    let mut request = Vec::new();
    let mut chunk = [0_u8; 4096];
    let header_end = loop {
        let count = stream.read(&mut chunk).unwrap();
        assert_ne!(count, 0, "client closed before request headers");
        request.extend_from_slice(&chunk[..count]);
        if let Some(index) = request.windows(4).position(|window| window == b"\r\n\r\n") {
            break index + 4;
        }
    };
    let headers = String::from_utf8_lossy(&request[..header_end]);
    let content_length = headers
        .lines()
        .find_map(|line| {
            let (name, value) = line.split_once(':')?;
            name.eq_ignore_ascii_case("content-length")
                .then(|| value.trim().parse::<usize>().ok())
                .flatten()
        })
        .unwrap_or(0);
    while request.len() < header_end + content_length {
        let count = stream.read(&mut chunk).unwrap();
        assert_ne!(count, 0, "client closed before request body");
        request.extend_from_slice(&chunk[..count]);
    }
}

fn server_observes_close(stream: &mut TcpStream) -> bool {
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    let mut byte = [0_u8; 1];
    matches!(stream.read(&mut byte), Ok(0))
}
