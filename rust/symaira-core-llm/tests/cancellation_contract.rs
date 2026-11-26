#![deny(unsafe_code)]

#[path = "support/cancellation.rs"]
mod cancellation;

use cancellation::{bind, cancel_and_check_close, fixture_ready, stall};
use serde_json::Value;
use std::net::TcpListener;
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
    // The listener queues any connections until all the calls have run.
    assert!(
        matches!(
            listener.accept(),
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock
        ),
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

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn cancellation_drops_embedding_discovery_and_ollama_stream_reads() {
    let incomplete_json = chunked_reply("{");
    for (phase, reply) in [
        ("embedding waiting for headers", &[][..]),
        ("embedding waiting for body", incomplete_json.as_bytes()),
    ] {
        let (url, listener) = bind().await;
        let client = ClientBuilder::new(lookup("openai").unwrap().clone(), "")
            .base_url(format!("{url}/v1"))
            .api_key("dummy-key")
            .build()
            .unwrap();
        let token = CancellationToken::new();
        let worker_token = token.clone();
        let worker = tokio::spawn(async move {
            client
                .embed_cancellable(&worker_token, "", &["input".into()], None)
                .await
        });
        let stream = stall(listener, reply, phase).await;
        let error = cancel_and_check_close(&token, worker, stream, phase).await;
        assert_eq!(error.code, ErrorCode::TransportError);
        assert_eq!(error.detail, "llmkit: context canceled");
    }

    let (url, listener) = bind().await;
    let client = ClientBuilder::new(lookup("openrouter").unwrap().clone(), "")
        .base_url(format!("{url}/api/v1"))
        .api_key("dummy-key")
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let worker = tokio::spawn(async move { client.list_models_cancellable(&worker_token).await });
    let phase = "model discovery";
    let stream = stall(listener, incomplete_json.as_bytes(), phase).await;
    let error = cancel_and_check_close(&token, worker, stream, phase).await;
    assert_eq!(error.code, ErrorCode::TransportError);
    assert_eq!(error.detail, "llmkit: context canceled");

    let first_record = "{\"model\":\"llama3.1\",\"response\":\"piece\",\"done\":false}\n";
    let (url, listener) = bind().await;
    let client = ClientBuilder::new(lookup("ollama").unwrap().clone(), "")
        .base_url(url)
        .build()
        .unwrap();
    let token = CancellationToken::new();
    let worker_token = token.clone();
    let (seen_tx, seen_rx) = tokio::sync::oneshot::channel();
    let mut seen_tx = Some(seen_tx);
    let worker = tokio::spawn(async move {
        client
            .generate_cancellable(
                &worker_token,
                "",
                "prompt",
                &GenerateOption::default(),
                move |_| {
                    seen_tx.take().unwrap().send(()).unwrap();
                    Ok(())
                },
            )
            .await
    });
    let stream = stall(
        listener,
        chunked_reply(first_record).as_bytes(),
        "Ollama stream",
    )
    .await;
    fixture_ready("Ollama first record", seen_rx)
        .await
        .expect("Ollama stream ended before delivering its first record");
    let error = cancel_and_check_close(&token, worker, stream, "Ollama stream").await;
    assert_eq!(error.code, ErrorCode::TransportError);
    assert!(
        error
            .detail
            .contains("stream interrupted: context canceled")
    );
}

fn chunked_reply(body: &str) -> String {
    format!(
        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nTransfer-Encoding: chunked\r\nConnection: keep-alive\r\n\r\n{:X}\r\n{body}\r\n",
        body.len()
    )
}
