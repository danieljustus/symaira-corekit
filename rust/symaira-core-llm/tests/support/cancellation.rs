use std::fmt::Debug;
use std::future::Future;
use std::io::ErrorKind;
use std::time::Duration;
use symaira_core_llm::{CancellationToken, Error, Result};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};
use tokio::task::JoinHandle;
use tokio::time::{Instant, timeout, timeout_at};

const FIXTURE_START_TIMEOUT: Duration = Duration::from_secs(15);

pub async fn bind() -> (String, TcpListener) {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    (format!("http://{address}"), listener)
}

pub async fn fixture_ready<T>(phase: &str, ready: impl Future<Output = T>) -> T {
    timeout(FIXTURE_START_TIMEOUT, ready)
        .await
        .unwrap_or_else(|_| panic!("{phase}: fixture startup timed out"))
}

pub async fn stall(listener: TcpListener, reply: &[u8], phase: &str) -> TcpStream {
    // Drive the already-bound listener in the test, not a separate server thread.
    fixture_ready(phase, async {
        let (mut stream, _) = listener.accept().await.unwrap();
        read_request(&mut stream).await;
        stream.write_all(reply).await.unwrap();
        stream
    })
    .await
}

pub async fn cancel_and_check_close<T: Debug>(
    token: &CancellationToken,
    worker: JoinHandle<Result<T>>,
    mut stream: TcpStream,
    phase: &str,
) -> Error {
    // Neither deadline includes accept, request I/O, or first-record delivery.
    let canceled_at = Instant::now();
    token.cancel();
    let error = timeout_at(canceled_at + Duration::from_secs(2), worker)
        .await
        .unwrap_or_else(|_| panic!("{phase}: canceled call did not return promptly"))
        .unwrap()
        .expect_err("canceled call unexpectedly succeeded");

    let mut byte = [0_u8; 1];
    match timeout_at(canceled_at + Duration::from_secs(5), stream.read(&mut byte)).await {
        Ok(Ok(0)) => {}
        Ok(Err(error)) if error.kind() == ErrorKind::ConnectionReset => {}
        Ok(outcome) => panic!("{phase}: expected FIN or RST after cancellation, got {outcome:?}"),
        Err(_) => panic!("{phase}: connection stayed open after cancellation"),
    }
    error
}

async fn read_request(stream: &mut TcpStream) {
    let mut request = Vec::new();
    let mut chunk = [0_u8; 4096];
    let header_end = loop {
        let count = stream.read(&mut chunk).await.unwrap();
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
        let count = stream.read(&mut chunk).await.unwrap();
        assert_ne!(count, 0, "client closed before request body");
        request.extend_from_slice(&chunk[..count]);
    }
}
