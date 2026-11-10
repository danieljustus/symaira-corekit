# Symaira CoreKit Swift package (swift/) — build/test entrypoints.
#
# The manifest lives at the repository root (SwiftPM resolves remote packages
# only from there), so swift commands run with --package-path pointing at it.
# The root Makefile delegates its swift-* targets here.
#
# Command Line Tools ship no XCTest and no SwiftUI macro plugins, so a bare
# `swift build` fails whenever xcode-select points at
# /Library/Developer/CommandLineTools. Rather than requiring every developer
# to change a machine-wide setting, these targets resolve a full Xcode
# toolchain themselves and export DEVELOPER_DIR for the child process only.
#
# Precedence: an explicit DEVELOPER_DIR wins, then the active xcode-select
# path if it is a real Xcode, then Xcode.app, then Xcode-beta.app.

SWIFT ?= swift
PACKAGE_PATH ?= ..

XCODE_DIR := $(shell \
	if [ -n "$$DEVELOPER_DIR" ]; then \
		echo "$$DEVELOPER_DIR"; \
	elif xcode-select -p 2>/dev/null | grep -qv CommandLineTools; then \
		xcode-select -p 2>/dev/null; \
	elif [ -d /Applications/Xcode.app/Contents/Developer ]; then \
		echo /Applications/Xcode.app/Contents/Developer; \
	elif [ -d /Applications/Xcode-beta.app/Contents/Developer ]; then \
		echo /Applications/Xcode-beta.app/Contents/Developer; \
	fi)

ifneq ($(XCODE_DIR),)
export DEVELOPER_DIR := $(XCODE_DIR)
endif

# Prefer the selected Xcode; a standalone installation on PATH is the fallback.
SWIFT_FORMAT ?= $(shell DEVELOPER_DIR="$(XCODE_DIR)" xcrun --find swift-format 2>/dev/null || command -v swift-format)

.PHONY: help build build-tvos test test-make lint format toolchain formatter

## help: List available targets
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'

## toolchain: Show which Swift toolchain the other targets will use
toolchain:
	@if [ -z "$(XCODE_DIR)" ]; then \
		echo "No full Xcode toolchain found."; \
		echo "Install Xcode, or run targets with DEVELOPER_DIR set explicitly."; \
		exit 1; \
	fi
	@echo "DEVELOPER_DIR = $(XCODE_DIR)"
	@$(SWIFT) --version

## build: Build all library targets
build: toolchain
	$(SWIFT) build --package-path $(PACKAGE_PATH)

## build-tvos: Build shared UI and keychain for tvOS Simulator
build-tvos: toolchain
	cd $(PACKAGE_PATH) && xcodebuild -scheme SymairaTheme -destination 'generic/platform=tvOS Simulator' CODE_SIGNING_ALLOWED=NO build
	cd $(PACKAGE_PATH) && xcodebuild -scheme SymairaKeychain -destination 'generic/platform=tvOS Simulator' CODE_SIGNING_ALLOWED=NO build

## test: Run Makefile regressions and the Swift suite (needs full Xcode)
test: toolchain test-make
	$(SWIFT) test --package-path $(PACKAGE_PATH)

## test-make: Verify formatter discovery and failure propagation
test-make:
	python3 -B scripts/test_make_format.py

formatter:
	@if ! command -v "$(SWIFT_FORMAT)" >/dev/null 2>&1; then \
		echo "swift-format not found; install full Xcode or set SWIFT_FORMAT=/path/to/swift-format" >&2; \
		exit 1; \
	fi

## lint: Check formatting strictly without writing changes
lint: formatter
	"$(SWIFT_FORMAT)" lint --strict --configuration .swift-format --recursive Sources Tests

## format: Apply the same formatting rules checked by lint
format: formatter
	"$(SWIFT_FORMAT)" format --in-place --configuration .swift-format --recursive Sources Tests
