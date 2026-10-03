"""Actual TLS negotiation and owned readiness boundaries for native fixtures."""
import os
from pathlib import Path
import socket
import ssl
import tempfile
import unittest

from update_fixture_transport import tls_fixture, write_ready


class NativeTransportTests(unittest.TestCase):
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
