.PHONY: build test lint fmt-check clean consumer-drift

build:
	CGO_ENABLED=0 go build ./...

consumer-drift:
	./scripts/consumer-drift.sh

test:
	CGO_ENABLED=0 go test -race ./...

lint: fmt-check
	go vet ./...

fmt-check:
	@test -z "$$(gofmt -l .)" || (echo "gofmt diff found:" && gofmt -l . && exit 1)

clean:
	go clean -cache -testcache
	rm -rf vendor/
