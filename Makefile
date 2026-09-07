.PHONY: build test lint fmt-check clean consumer-drift golangci-lint rust-port-validate port-fixture-source-check port-oracle-selftest port-contract rust-lint rust-test rust-foundation-contract

build:
	CGO_ENABLED=0 go build ./...

consumer-drift:
	./scripts/consumer-drift.sh

rust-port-validate:
	python3 docs/rust-port/validate.py

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
