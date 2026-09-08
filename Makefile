.PHONY: build test lint fmt-check clean consumer-drift golangci-lint rust-port-validate port-fixture-source-check port-oracle-selftest port-contract rust-lint rust-test rust-foundation-contract rust-fs-secret-contract rust-mcp-contract rust-miri mcp-differential mcp-fuzz-smoke port-consumer-smoke

build:
	CGO_ENABLED=0 go build ./...

consumer-drift:
	./scripts/consumer-drift.sh

rust-port-validate:
	python3 scripts/rust-port/adoption.py --self-test
	python3 scripts/rust-port/bench.py --self-test
	python3 docs/rust-port/validate.py
	@set +e; \
	python3 scripts/rust-port/adoption.py --check --min-consumers 2; adoption_status=$$?; \
	python3 scripts/rust-port/bench.py --suite foundation --runs 50 --build-runs 10 --check; bench_status=$$?; \
	if [ $$adoption_status -ne 0 ] || [ $$bench_status -ne 0 ]; then \
		echo "RUST-005 validation failed (adoption=$$adoption_status benchmark=$$bench_status)" >&2; \
		exit 1; \
	fi

port-consumer-smoke:
	python3 scripts/rust-port/bench.py --suite foundation --smoke

port-fixture-source-check:
	python3 scripts/rust-port/generate.py --check-source
	python3 scripts/rust-port/generate.py --check

port-oracle-selftest:
	python3 scripts/rust-port/diff.py --self-test

port-contract: rust-port-validate port-fixture-source-check port-oracle-selftest
	cd scripts/rust-port/go-oracle && GOTOOLCHAIN=go1.26.6 go test ./...

rust-lint:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings

rust-test:
	cargo test --workspace --all-features --locked

rust-foundation-contract:
	python3 scripts/rust-port/generate.py --check
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 go test -count=1 ./versionkit ./exitcodes ./envutil ./logkit ./configkit
	cargo test -p symaira-contract-fixtures --all-features --locked
	cargo test -p symaira-core-foundation --all-features --locked

rust-fs-secret-contract:
	cargo fmt --all --check
	cargo test -p symaira-core-fs -p symaira-core-secretref --all-features --locked
	cargo clippy -p symaira-core-fs -p symaira-core-secretref --all-targets --all-features --locked -- -D warnings
	python3 scripts/rust-port/generate_fs_secret.py --check
	python3 scripts/rust-port/validate_fs_secret.py
	python3 scripts/rust-port/diff_fs_secret.py
	cargo audit
	cargo deny check
	@command -v cargo-miri >/dev/null 2>&1 && MIRIFLAGS=-Zmiri-disable-isolation cargo +nightly miri test -p symaira-core-fs -p symaira-core-secretref --all-features || { echo "cargo-miri is required for rust-fs-secret-contract"; exit 1; }

rust-mcp-contract:
	cargo fmt --all --check
	cargo check -p symaira-core-mcp --all-targets --all-features --locked
	cargo clippy -p symaira-core-mcp --all-targets --all-features --locked -- -D warnings
	cargo test -p symaira-core-mcp --all-features --locked

rust-miri:
	python3 scripts/rust-port/miri_gate.py --self-test
	python3 scripts/rust-port/miri_gate.py --negative-test
	python3 scripts/rust-port/miri_gate.py --run

mcp-differential:
	python3 scripts/rust-port/mcp-differential.py --check

mcp-fuzz-smoke:
	cargo fuzz --version | grep -F 'cargo-fuzz 0.13.2'
	@FUZZ_CORPUS=$$(mktemp -d); \
	trap 'rm -rf "$$FUZZ_CORPUS"' EXIT; \
	cp fuzz/corpus/mcp_frame/* "$$FUZZ_CORPUS"/; \
	cd fuzz && cargo +nightly-2026-09-03 fuzz run mcp-frame "$$FUZZ_CORPUS" --sanitizer none -- -runs=100

test:
	CGO_ENABLED=0 go test -race ./...

golangci-lint:
	@command -v golangci-lint >/dev/null 2>&1 || { echo "golangci-lint not found; install from https://golangci-lint.run"; exit 1; }
	golangci-lint run --timeout 5m

lint: golangci-lint fmt-check
	go vet ./...

fmt-check:
	@test -z "$$(gofmt -l .)" || (echo "gofmt diff found:" && gofmt -l . && exit 1)

clean:
	go clean -cache -testcache
	rm -rf vendor/
