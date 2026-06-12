// Package envutil provides environment variable helpers with fallback support.
package envutil

import "os"

// Getenv returns the value of the primary environment variable. If the primary
// is empty or unset, it tries each legacy alias in order and returns the first
// non-empty value found. Returns "" if none are set.
func Getenv(primary string, legacy ...string) string {
	if v := os.Getenv(primary); v != "" {
		return v
	}
	for _, key := range legacy {
		if v := os.Getenv(key); v != "" {
			return v
		}
	}
	return ""
}

// Unsetenv removes the named environment variable from the environment.
// It is a thin wrapper around os.Unsetenv that returns any error.
func Unsetenv(key string) error {
	return os.Unsetenv(key)
}
