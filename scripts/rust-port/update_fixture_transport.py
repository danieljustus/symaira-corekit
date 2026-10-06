"""Disposable native TLS fixtures for Go-free Rust update acceptance.

These endpoints reproduce the controlled transports used by the original Go
oracles. Their ephemeral identity is trusted only by explicit test clients.
Nothing here verifies a signature or supplies expected Go observations.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import ssl
import tempfile
import threading
import time
from urllib.parse import urlsplit

from bounded_oracle_process import BoundedProcessError, run_bounded


def create_identity(command, directory, mode, *, timeout: float = 45):
    """Retain safe setup diagnostics, never a private key or child output."""
    started = time.monotonic()
    result = None
    error_type = None
    try:
        result = run_bounded(command, cwd=directory, env=dict(os.environ),
                             timeout=timeout, limit=64 * 1024)
    except (BoundedProcessError, OSError) as exc:
        result = getattr(exc, "result", None)
        error_type = type(exc).__name__
    diagnostic = {
        "event": "tls_identity_setup", "mode": mode,
        "algorithm": "rsa:2048" if mode == "tls" else "ed25519",
        "openssl_executable": command[0], "system": platform.system(),
        "python_ssl_version": ssl.OPENSSL_VERSION,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "timeout_seconds": timeout, "error_type": error_type,
        "key_file_present": (directory / "key.pem").is_file(),
        "certificate_file_present": (directory / "cert.pem").is_file(),
    }
    if result is not None:
        diagnostic.update({name: result[name] for name in (
            "returncode", "timed_out", "output_exceeded", "cleanup_verified")})
        diagnostic.update(stdout_bytes=len(result["stdout"]), stderr_bytes=len(result["stderr"]),
                          prime_progress={chr(value): result["stderr"].count(bytes([value]))
                                          for value in b".+*"})
    print(json.dumps(diagnostic, sort_keys=True), flush=True)
    if (error_type or result is None or result["returncode"] != 0 or result["timed_out"]
            or result["output_exceeded"] or not result["cleanup_verified"]):
        raise RuntimeError("ephemeral TLS identity creation failed; see tls_identity_setup record") from None


def write_ready(name, private_tmp):
    # Rust canonicalizes local Windows paths to \\?\ drive spelling. Python's
    # lexical relative-path check treats that prefix as a different drive.
    # Normalize only that equivalent local-drive form; UNC paths stay rejected.
    if os.name == "nt" and re.match(r"^\\\\\?\\[A-Za-z]:[\\/]", name):
        name = name[4:]
    requested = Path(name)
    root = private_tmp.resolve(strict=True)
    if not requested.is_absolute() or not requested.is_relative_to(root):
        raise ValueError(f"readiness path escapes disposable TMPDIR: requested={requested!s}; root={root!s}")
    relative = requested.relative_to(root)
    current = root
    for component in relative.parts:
        current = current / component
        if current.is_symlink():
            raise ValueError("readiness path traverses a symlink")
    if not requested.parent.resolve(strict=True).is_relative_to(root):
        raise ValueError("readiness parent escapes disposable TMPDIR")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(requested, flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"ready")


@contextmanager
def tls_fixture(mode, private_tmp):
    if mode not in ("tls", "tls12", "tls13", "cancellation"):
        raise ValueError("unknown fixture transport")
    openssl = shutil.which("openssl")
    if platform.system() == "Darwin":
        # Apple's legacy LibreSSL CLI may lack req -addext. The supported
        # hosted image already provides modern Homebrew OpenSSL; use that pin
        # without installing a new runtime or changing production TLS.
        for candidate in ("/opt/homebrew/opt/openssl@3/bin/openssl", "/usr/local/opt/openssl@3/bin/openssl"):
            if Path(candidate).is_file():
                openssl = candidate
                break
    if openssl is None:
        raise RuntimeError("native TLS fixture requires the existing OpenSSL CLI")
    with tempfile.TemporaryDirectory(prefix="corekit-test-tls-", dir=private_tmp) as directory:
        directory = Path(directory)
        key = directory / "key.pem"
        certificate = directory / "cert.pem"
        # The original untrusted httptest certificate uses RSA. Its explicitly
        # trusted TLS-version fixtures use Ed25519. Match that distinction so
        # Windows' system verifier reports the original trust-chain failure,
        # rather than an unsupported untrusted signing algorithm.
        untrusted = mode == "tls"
        create_identity(
            [openssl, "req", "-new", "-x509", "-newkey", "rsa:2048" if untrusted else "ed25519", "-nodes",
             "-keyout", str(key), "-out", str(certificate), "-days", "1",
             "-subj", "/CN=corekit-disposable-loopback",
             "-addext", "subjectAltName=IP:127.0.0.1",
             "-addext", "basicConstraints=critical,CA:TRUE" if untrusted else "basicConstraints=critical,CA:FALSE",
             "-addext", "keyUsage=critical,digitalSignature,keyCertSign" if untrusted else "keyUsage=critical,digitalSignature",
             "-addext", "extendedKeyUsage=serverAuth"],
            # Bound identity setup separately from the unchanged HTTP and
            # cancellation deadlines; native Windows RSA generation has
            # exceeded 15 seconds on a loaded hosted runner.
            directory, mode, timeout=45,
        )
        key.chmod(0o600)
        der = directory / "cert.der"
        der.write_bytes(ssl.PEM_cert_to_DER_cert(certificate.read_text(encoding="ascii")))
        stopped = threading.Event()
        failures = []

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *_):
                pass

            def complete(self, status, body=b"", headers=()):
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.close_connection = True

            def do_GET(self):
                path = urlsplit(self.path).path
                try:
                    if mode == "cancellation":
                        if path in ("/asset-body/checksums", "/apply/checksums"):
                            body = (hashlib.sha256(b"new").hexdigest() + "  tool_linux_amd64\n").encode()
                            self.complete(200, body)
                        elif path == "/apply/asset":
                            self.complete(200, b"new")
                        elif path.startswith("/injected"):
                            self.complete(200, b"injected")
                        else:
                            if path.startswith(("/body", "/asset-body")):
                                self.send_response(200)
                                self.send_header("Transfer-Encoding", "chunked")
                                self.end_headers()
                                self.wfile.flush()
                            ready = self.headers.get("X-Ready")
                            if not ready:
                                raise ValueError("missing test readiness path")
                            write_ready(ready, private_tmp)
                            # Readiness, rather than elapsed sleep, gates Rust's
                            # cancellation. A disconnect ends this owned handler.
                            self.connection.settimeout(0.1)
                            while not stopped.is_set():
                                try:
                                    if not self.connection.recv(1):
                                        break
                                except socket.timeout:
                                    continue
                            self.close_connection = True
                    elif "_foreign_" in path:
                        self.complete(302, headers=(("Location", "//evil.example/steal"),))
                    elif "_downgrade_" in path:
                        self.complete(302, headers=(("Location", "http://github.com/insecure"),))
                    elif "_404_" in path:
                        self.complete(404)
                    elif "_large_" in path:
                        self.complete(200, b"x" * ((1 << 20) + 1))
                    elif path.endswith(".sig"):
                        self.complete(200, b"signature-bytes\n")
                    elif path.endswith(".pem"):
                        self.complete(200, b"certificate-bytes\n")
                    else:
                        self.complete(200, b'{"tag_name":"v1.2.4"}')
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError):
                    self.close_connection = True
                except Exception as error:
                    failures.append(error)
                    self.close_connection = True

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        version = ssl.TLSVersion.TLSv1_2 if mode == "tls12" else ssl.TLSVersion.TLSv1_3
        context.minimum_version = version
        context.maximum_version = version
        context.load_cert_chain(certificate, key)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield {"url": f"https://127.0.0.1:{server.server_port}", "cert": str(der)}
        finally:
            stopped.set()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError("owned TLS listener did not stop")
            if failures:
                raise RuntimeError("native TLS fixture failed") from failures[0]
