.PHONY: build test lint fmt-check clean consumer-drift golangci-lint

build:
	CGO_ENABLED=0 go build ./...

consumer-drift:
	./scripts/consumer-drift.sh

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
