# Test-only untrusted RSA loopback identity

`key.pem` and `cert.pem` are a **test-only** RSA-2048 self-signed CA certificate
(`CN=corekit-disposable-loopback`, SAN `IP:127.0.0.1`, `CA:TRUE`, `sha256WithRSA`,
100-year validity). They protect nothing and must never be trusted outside the
native update-replay fixtures (`../../update_fixture_transport.py`).

Purpose: reproduce the original untrusted RSA `httptest` certificate (the system
verifier must reject it without explicit trust) while avoiding runtime RSA key
generation through an OpenSSL subprocess (issue #404).

Regenerate only if the contract changes:

    openssl req -new -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem \
      -days 36500 -subj /CN=corekit-disposable-loopback \
      -addext subjectAltName=IP:127.0.0.1 -addext basicConstraints=critical,CA:TRUE \
      -addext keyUsage=critical,digitalSignature,keyCertSign -addext extendedKeyUsage=serverAuth
