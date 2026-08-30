package secretref

import "errors"

// ErrNoReference is returned when both the reference and its default are empty.
var ErrNoReference = errors.New("no credential reference or default provided")

// ErrTimeout indicates a symvault/keychain subprocess exceeded its context
// deadline (DefaultTimeout when the caller supplied none).
var ErrTimeout = errors.New("secretref: subprocess timed out")

// ErrSymvaultNotFound is returned when the symvault binary is not on PATH.
// Resolution degrades to this error instead of blocking or panicking.
var ErrSymvaultNotFound = errors.New("symvault binary not found on PATH")

// ErrKeychainUnsupported is returned when a keychain:// reference is
// resolved on a non-macOS platform.
var ErrKeychainUnsupported = errors.New("keychain:// references are only resolvable on macOS")
