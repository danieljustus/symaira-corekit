.PHONY: build test lint fmt-check clean consumer-drift port-consumer-verify consumer-pin-regression golangci-lint rust-port-validate port-fixture-source-check port-oracle-selftest port-contract rust-lint rust-test rust-foundation-contract rust-fs-secret-contract rust-mcp-contract rust-mcpcfg-contract rust-llm-contract rust-update-version-contract rust-update-contract rust-update-signed-contract rust-release-contract rust-miri rust-hardening mcp-differential mcp-fuzz-smoke port-consumer-smoke rust-sqlite-refreeze

DEV_EXTERNAL := $(if $(wildcard $(HOME)/.local/bin/dev-external),$(HOME)/.local/bin/dev-external,)
CARGO_RUN := $(if $(DEV_EXTERNAL),$(DEV_EXTERNAL) cargo,cargo)
GO_RUN := $(if $(DEV_EXTERNAL),$(DEV_EXTERNAL) go,go)

build:
	CGO_ENABLED=0 go build ./...

consumer-drift:
	./scripts/consumer-drift.sh

port-consumer-verify:
	python3 port/consumer/verify.py --released-consumers

consumer-pin-regression:
	./scripts/test-check-consumer-pins.sh

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
	python3 -m unittest discover -s scripts/rust-port -p test_fixture_preservation.py

port-oracle-selftest:
	python3 scripts/rust-port/diff.py --self-test

port-contract: rust-port-validate port-fixture-source-check port-oracle-selftest
	python3 -m unittest discover -s scripts/rust-port -p test_retirement_routing.py
	cd scripts/rust-port/go-oracle && GOTOOLCHAIN=go1.26.6 go test ./...

rust-lint:
	cargo fmt --all --check
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings

rust-test:
	cargo test --workspace --all-features --locked

rust-foundation-contract:
	@if [ "$$GO_ORACLE" = 1 ]; then \
		python3 scripts/rust-port/generate.py --check && \
		GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 go test -count=1 ./versionkit ./exitcodes ./envutil ./logkit ./configkit; \
	fi
	python3 scripts/rust-port/frozen_core_replay.py --family foundation

.PHONY: rust-sqlite-contract
rust-sqlite-contract:
	cargo fmt --manifest-path "$(CURDIR)/Cargo.toml" --all --check
	cargo test --manifest-path "$(CURDIR)/Cargo.toml" -p symaira-core-sqlite --all-features --locked
	python3 -m unittest discover -s scripts/rust-port/sqlite -p 'test_*.py'
	python3 -m unittest discover -s scripts/rust-port -p 'test_rust_sqlite_provenance.py'
	@if [ "$$GO_ORACLE" = 1 ]; then \
		python3 scripts/rust-port/sqlite/diff.py --typed-errors --output target/sqlite-contract-report.json; \
	fi
	python3 scripts/rust-port/frozen_sqlite_replay.py

# Documented recapture path for a genuine port-input change (see
# docs/rust-port/adr-rust-003-candidate-source-scope.md). Never run
# automatically: it regenerates the frozen manifest and writes a new
# differential capture, and generation is not approval. The new manifest and
# capture require independent review, and the acceptance tests are repointed in
# a separate reviewed change.
.PHONY: rust-sqlite-refreeze
rust-sqlite-refreeze:
	@test "$$GO_ORACLE" = 1 || { echo "live SQLite recapture requires GO_ORACLE=1" >&2; exit 1; }
	@echo "REFREEZE: regenerates the frozen manifest and a new capture; review is still required."
	python3 scripts/rust-port/sqlite/candidate.py --output testdata/rust-port/sqlite/candidate-source.json
	python3 scripts/rust-port/sqlite/diff.py --typed-errors --output testdata/rust-port/sqlite/differential-macos-refreeze-$$(date -u +%Y%m%dT%H%M%SZ).json
	@echo "REFROZEN: review both artifacts independently, then repoint the acceptance tests."

.PHONY: rust-fs-secret-frozen-contract rust-fs-secret-live-oracle
rust-fs-secret-frozen-contract:
	cargo fmt --all --check
	cargo test -p symaira-core-fs -p symaira-core-secretref --all-features --locked
	cargo clippy -p symaira-core-fs -p symaira-core-secretref --all-targets --all-features --locked -- -D warnings
	python3 -c 'import pathlib,tomllib; r=pathlib.Path.cwd(); assert (r/"contracts/secret_refs.json").read_bytes()==(r/"rust/symaira-core-secretref/contracts/secret_refs.json").read_bytes(); assert all(tomllib.loads((r/"rust"/c/"Cargo.toml").read_text())["package"]["publish"] is False for c in ("symaira-core-fs","symaira-core-secretref"))'
	python3 -m unittest discover -s scripts/rust-port -p 'test_fs_secret_oracle.py'
	python3 scripts/rust-port/fs_secret_oracle.py

# Preserve the original live evidence path, but never invoke it implicitly.
rust-fs-secret-live-oracle:
	@test "$$GO_ORACLE" = 1 || { echo "live FS/SEC oracle requires GO_ORACLE=1" >&2; exit 1; }
	python3 scripts/rust-port/generate_fs_secret.py --check
	python3 scripts/rust-port/validate_fs_secret.py
	python3 scripts/rust-port/diff_fs_secret.py
	python3 scripts/rust-port/fs-path-control-differential.py

# Keep the complete security gate; portable replay does not replace Miri.
rust-fs-secret-contract: rust-fs-secret-frozen-contract
	cargo audit
	cargo deny check
	@command -v cargo-miri >/dev/null 2>&1 && MIRIFLAGS=-Zmiri-disable-isolation cargo +nightly miri test -p symaira-core-fs -p symaira-core-secretref --all-features || { echo "cargo-miri is required for rust-fs-secret-contract"; exit 1; }

rust-mcp-contract:
	cargo fmt --all --check
	cargo check -p symaira-core-mcp --all-targets --all-features --locked
	cargo clippy -p symaira-core-mcp --all-targets --all-features --locked -- -D warnings
	cargo test -p symaira-core-mcp --all-features --locked

rust-mcpcfg-contract:
	cargo fmt --all --check
	cargo check -p symaira-core-mcpcfg --all-targets --all-features --locked
	cargo clippy -p symaira-core-mcpcfg --all-targets --all-features --locked -- -D warnings
	cargo test -p symaira-core-mcpcfg --all-features --locked

rust-llm-contract:
	@if [ "$$GO_ORACLE" = 1 ]; then \
		GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 $(GO_RUN) test -count=1 ./llmkit/... ./ollamakit/... ./secretref ./contracts && \
		python3 scripts/rust-port/llm-differential.py; \
	fi
	python3 scripts/rust-port/frozen_core_replay.py --family llm
	$(CARGO_RUN) fmt --all --check
	$(CARGO_RUN) clippy --manifest-path "$(CURDIR)/Cargo.toml" -p symaira-core-llm --all-targets --all-features --locked -- -D warnings

rust-update-version-contract:
	@if [ "$$GO_ORACLE" = 1 ]; then GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 $(GO_RUN) test -count=1 ./updatecheck; fi
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-version-differential.py
	$(CARGO_RUN) fmt --all --check
	$(CARGO_RUN) clippy --manifest-path "$(CURDIR)/Cargo.toml" -p symaira-core-update --all-targets --all-features --locked -- -D warnings
	$(CARGO_RUN) test --manifest-path "$(CURDIR)/Cargo.toml" -p symaira-core-update --all-targets --all-features --locked

# Update replay and production Apply against frozen native Go observations, with
# mutations rejected. Live regeneration requires explicit GO_ORACLE=1.
# The separate signed-release acceptance gate runs in CI
# and can be invoked locally when the verifier and its trust endpoints exist.
rust-update-contract: rust-update-version-contract
	python3 -m unittest discover -s scripts/rust-port -p 'test_update_harness.py'
	python3 -m unittest discover -s scripts/rust-port -p 'test_frozen_update_replay.py'
	@if [ "$$GO_ORACLE" = 1 ]; then GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 $(GO_RUN) test -count=1 ./updatecheck/...; fi
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-response-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-response-differential.py --negative-control
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-request-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-cache-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-cache-differential.py --negative-control
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/install-method-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/install-method-differential.py --negative-control
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-extract-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-extract-differential.py --negative-control
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/cosign-contract-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-apply-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-swap-differential.py
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-checker-differential.py --check
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/update-cancellation-differential.py --check

# Real Cosign and end-to-end Apply. Requires curl, Cosign and network;
# replaces only an isolated disposable target, never an installed binary.
rust-update-signed-contract:
	GOTOOLCHAIN=go1.26.6 CGO_ENABLED=0 python3 scripts/rust-port/cosign-valid-differential.py

# Complete native functional replay. FS security/Miri and workspace hardening
# retain their separate required CI lanes; Miri is not a native Windows gate.
# The real signed-release gate needs pinned Cosign, curl and public trust access.
.PHONY: rust-contracts
rust-contracts: rust-foundation-contract rust-fs-secret-frozen-contract rust-mcp-contract rust-mcpcfg-contract mcp-differential mcpcfg-differential rust-llm-contract rust-sqlite-contract rust-update-contract rust-update-signed-contract

.PHONY: mcpcfg-differential
mcpcfg-differential:
	python3 scripts/rust-port/mcpcfg-differential.py --check

rust-release-contract: consumer-pin-regression
	cargo semver-checks check-release
	python3 -m unittest discover -s port/release -p 'test_*.py'
	python3 -m unittest discover -s port/consumer -p 'test_*.py'
	python3 port/release/verify.py --dry-run

rust-miri:
	python3 scripts/rust-port/miri_gate.py --self-test
	python3 scripts/rust-port/miri_gate.py --negative-test
	python3 scripts/rust-port/miri_gate.py --run

rust-hardening:
	cargo fmt --all --check
	cargo check --workspace --all-targets --all-features --locked
	cargo clippy --workspace --all-targets --all-features --locked -- -D warnings
	cargo nextest run --workspace --all-features --locked
	cargo test --workspace --doc --all-features --locked
	# cargo-hack --no-dev-deps rewrites manifests temporarily and must refresh its lock view.
	cargo hack check --workspace --each-feature --no-dev-deps
	cargo llvm-cov --workspace --all-features --no-report
	cargo audit
	cargo deny check
	python3 docs/rust-port/validate.py
	make build
	make test lint

mcp-differential:
	python3 scripts/rust-port/mcp-differential.py --check

mcp-fuzz-smoke:
	cargo fuzz --version | grep -F 'cargo-fuzz 0.13.2'
	@FUZZ_CORPUS=$$(mktemp -d); \
	trap 'rm -rf "$$FUZZ_CORPUS"' EXIT; \
	cp fuzz/corpus/mcp_frame/* "$$FUZZ_CORPUS"/; \
	cd fuzz && cargo +nightly-2026-09-03 fuzz run mcp-frame "$$FUZZ_CORPUS" --sanitizer none -- -runs=100

test:
	CGO_ENABLED=1 go test -race ./...

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
