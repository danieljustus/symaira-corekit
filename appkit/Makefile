# Symaira AppKit — build/test entrypoints.
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

.PHONY: help build test lint toolchain

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
	$(SWIFT) build

## test: Run the test suite (needs XCTest, hence a full Xcode)
test: toolchain
	$(SWIFT) test

## lint: Check formatting without writing changes
lint:
	@if command -v swift-format >/dev/null 2>&1; then \
		swift-format lint --recursive Sources Tests; \
	else \
		echo "swift-format not installed; skipping"; \
	fi
