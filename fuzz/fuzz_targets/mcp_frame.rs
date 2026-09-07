#![no_main]

use std::io::{self, Cursor, Write};

use libfuzzer_sys::fuzz_target;
use symaira_core_mcp::Server;

struct Sink;

impl Write for Sink {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fuzz_target!(|input: &[u8]| {
    // Cursor reaches EOF, so this exercises both line and Content-Length paths
    // without leaving a blocking reader behind in the libFuzzer process.
    let server = Server::new("fuzz", "1");
    let _ = server.serve_io(Cursor::new(input.to_vec()), Sink);
});
