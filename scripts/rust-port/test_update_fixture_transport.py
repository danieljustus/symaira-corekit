"""Actual TLS negotiation and owned readiness boundaries for native fixtures."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import tempfile
import time
import unittest
from unittest import mock

import update_fixture_transport as transport
from update_fixture_transport import create_identity, tls_fixture, write_ready


class NativeTransportTests(unittest.TestCase):
    def test_identity_failures_are_bounded_diagnostic_and_never_accept_partial_material(self):
        secret = "PRIVATE_TEST_CANARY_DO_NOT_LOG"
        code = ("import os,pathlib,time; "
                "assert os.read(0, 1) == b''; "
                "pathlib.Path('key.pem').write_text('disposable partial key'); "
                f"os.write(1, {secret.encode()!r}); os.write(2, {b'..+*' + secret.encode()!r}); ")
        for label, tail, timeout in (
            ("timeout", "time.sleep(30)", 0.3),
            ("nonzero", "raise SystemExit(7)", 4),
            ("overflow", "os.write(2, b'X' * (128 * 1024))", 4),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as name:
                output = io.StringIO()
                started = time.monotonic()
                with redirect_stdout(output), self.assertRaisesRegex(RuntimeError, "tls_identity_setup") as caught:
                    create_identity([sys.executable, "-c", code + tail], Path(name), "tls", timeout=timeout)
                self.assertLess(time.monotonic() - started, 6)
                record = json.loads(output.getvalue())
                self.assertEqual(record["event"], "tls_identity_setup")
                self.assertEqual(record["algorithm"], "rsa:2048")
                self.assertEqual(record["timeout_seconds"], timeout)
                self.assertTrue(record["key_file_present"])
                self.assertFalse(record["certificate_file_present"])
                self.assertTrue(record["cleanup_verified"])
                self.assertIsNotNone(record["returncode"])
                self.assertNotIn(secret, output.getvalue() + str(caught.exception))
                self.assertEqual(record["prime_progress"], {".": 2, "+": 1, "*": 1})
                if label == "timeout":
                    self.assertTrue(record["timed_out"])
                elif label == "nonzero":
                    self.assertEqual(record["returncode"], 7)
                else:
                    self.assertTrue(record["output_exceeded"])
                    self.assertLessEqual(record["stderr_bytes"], 64 * 1024)
        # Structural failure injection is not a substitute for the native
        # Windows cleanup acceptance tests or the real child controls above.
        result = {"returncode": 0, "timed_out": False, "output_exceeded": False,
                  "cleanup_verified": False, "stdout": b"", "stderr": b""}
        with tempfile.TemporaryDirectory() as name, mock.patch.object(transport, "run_bounded", return_value=result):
            with redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
                create_identity([sys.executable], Path(name), "tls")
        with tempfile.TemporaryDirectory() as name, mock.patch.object(transport, "run_bounded", side_effect=OSError(secret)):
            output = io.StringIO()
            with redirect_stdout(output), self.assertRaises(RuntimeError) as caught:
                create_identity([sys.executable], Path(name), "tls")
            record = json.loads(output.getvalue())
            self.assertEqual(record["error_type"], "OSError")
            self.assertNotIn("cleanup_verified", record)
            self.assertNotIn(secret, output.getvalue() + str(caught.exception))

    def test_untrusted_rsa_endpoint_rejects_default_roots_and_accepts_explicit_trust(self):
        with tempfile.TemporaryDirectory() as name:
            with tls_fixture("tls", Path(name).resolve(strict=True)) as connection:
                port = int(connection["url"].rsplit(":", 1)[1])
                with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        ssl.create_default_context().wrap_socket(stream, server_hostname="127.0.0.1")
                pem = ssl.DER_cert_to_PEM_cert(Path(connection["cert"]).read_bytes())
                context = ssl.create_default_context(cadata=pem)
                with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
                    with context.wrap_socket(stream, server_hostname="127.0.0.1") as secured:
                        self.assertEqual(secured.version(), "TLSv1.3")
                        secured.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                        body = bytearray()
                        while chunk := secured.recv(4096):
                            body.extend(chunk)
                        self.assertIn(b'{"tag_name":"v1.2.4"}', body)

    def test_tls12_endpoint_rejects_tls13_and_accepts_trusted_weak_control(self):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            with tls_fixture("tls12", directory) as connection:
                port = int(connection["url"].rsplit(":", 1)[1])
                pem = ssl.DER_cert_to_PEM_cert(Path(connection["cert"]).read_bytes())
                context = ssl.create_default_context(cadata=pem)
                context.minimum_version = ssl.TLSVersion.TLSv1_3
                with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
                    with self.assertRaises(ssl.SSLError):
                        context.wrap_socket(stream, server_hostname="127.0.0.1")
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.maximum_version = ssl.TLSVersion.TLSv1_2
                with socket.create_connection(("127.0.0.1", port), timeout=2) as stream:
                    with context.wrap_socket(stream, server_hostname="127.0.0.1") as secured:
                        self.assertEqual(secured.version(), "TLSv1.2")
                        secured.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
                        body = bytearray()
                        while chunk := secured.recv(4096):
                            body.extend(chunk)
                        self.assertIn(b'{"tag_name":"v1.2.4"}', body)

    def test_ready_file_cannot_replace_existing_data_or_escape_private_root(self):
        with tempfile.TemporaryDirectory() as name, tempfile.TemporaryDirectory() as outside:
            directory = Path(name).resolve()
            ready = directory / "ready"
            write_ready(str(ready), directory)
            self.assertEqual(ready.read_bytes(), b"ready")
            with self.assertRaises(FileExistsError):
                write_ready(str(ready), directory)
            with self.assertRaises(ValueError):
                write_ready(str(Path(outside) / "escape"), directory)
            if os.name == "posix":
                self.assertEqual(ready.stat().st_mode & 0o777, 0o600)
                link = directory / "redirect"
                link.symlink_to(outside, target_is_directory=True)
                with self.assertRaises(ValueError):
                    write_ready(str(link / "escape"), directory)
            self.assertFalse((Path(outside) / "escape").exists())
            if os.name == "nt":
                prefixed = directory / "ready-canonical"
                write_ready("\\\\?\\" + str(prefixed), directory)
                self.assertEqual(prefixed.read_bytes(), b"ready")
                with self.assertRaises(ValueError):
                    write_ready("\\\\?\\" + str(Path(outside) / "escape"), directory)


if __name__ == "__main__":
    unittest.main()
