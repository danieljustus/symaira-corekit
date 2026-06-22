// Package configkit provides generic TOML configuration loading with env var overrides.
//
// Configuration is loaded in order of precedence (later overrides earlier):
//
//  1. Defaults (from caller-provided function)
//  2. Global TOML file (~/.config/{appName}/config.toml)
//  3. Project-local TOML file (./.{appName}.toml)
//  4. Environment variables ({PREFIX}_{SECTION}_{FIELD})
//
// Structs must use json tags for field name mapping:
//
//	type MyConfig struct {
//	    Server ServerConfig `json:"server"`
//	}
//	type ServerConfig struct {
//	    Port int `json:"port"`
//	}
//
// The Loader type provides sync.Once caching (Load reads once, caches forever)
// plus a Reload method for long-running servers that need hot config reload.
package configkit

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/BurntSushi/toml"
)

// Options configures the config loader.
type Options struct {
	// AppName is the application name (e.g., "symfetch").
	// Used as the default env var prefix (uppercased) and config file name.
	AppName string

	// EnvPrefix overrides the env var prefix. Default: uppercase AppName.
	// For nested structs, env vars are named {PREFIX}_{SECTION}_{FIELD}.
	EnvPrefix string

	// ConfigName overrides the config filename without extension.
	// Default: AppName. Global file: ~/.config/{ConfigName}/config.toml.
	// Project file: ./{ConfigName}.toml.
	ConfigName string
}

// DefaultPath returns the default global config file path for the given app name.
// Example: DefaultPath("symfetch") → "~/.config/symfetch/config.toml"
func DefaultPath(appName string) string {
	home, err := os.UserHomeDir()
	if err != nil {
		return filepath.Join(".config", appName, "config.toml")
	}
	return filepath.Join(home, ".config", appName, "config.toml")
}

// Loader provides cached config loading for type T.
// It implements sync.Once caching: Load reads from disk on the first call
// and returns the cached value on subsequent calls. Use Reload for hot reload.
type Loader[T any] struct {
	opts      Options
	defaults  func() *T
	once      sync.Once
	cached    *T
	cachedErr error
}

// NewLoader creates a config loader. defaults returns a *T with sensible default values.
func NewLoader[T any](opts Options, defaults func() *T) *Loader[T] {
	if opts.ConfigName == "" {
		opts.ConfigName = opts.AppName
	}
	return &Loader[T]{opts: opts, defaults: defaults}
}

// Load returns the config, loading and caching on first call.
// Subsequent calls return the cached value without re-reading from disk.
func (l *Loader[T]) Load() (*T, error) {
	l.once.Do(func() {
		l.cached, l.cachedErr = l.loadOnce()
	})
	return l.cached, l.cachedErr
}

// Reload reads a fresh config from disk (global + project + env vars),
// bypassing the cache. Intended for long-running servers that need hot reload.
func (l *Loader[T]) Reload() (*T, error) {
	return l.loadOnce()
}

// ResetCache clears the cached config so the next Load reads from disk.
// Intended for tests only.
func (l *Loader[T]) ResetCache() {
	l.cached = nil
	l.cachedErr = nil
	l.once = sync.Once{}
}

func (l *Loader[T]) loadOnce() (*T, error) {
	cfg := l.defaults()

	home, err := os.UserHomeDir()
	if err != nil {
		return cfg, fmt.Errorf("cannot determine home directory: %w", err)
	}

	// Global config: ~/.config/{appName}/config.toml
	globalPath := filepath.Join(home, ".config", l.opts.ConfigName, "config.toml")
	if err := mergeFile(cfg, globalPath); err != nil {
		return cfg, fmt.Errorf("global config error: %w", err)
	}

	// Project-local config: ./{appName}.toml
	cwd, err := os.Getwd()
	if err == nil {
		projectPath := filepath.Join(cwd, "."+l.opts.ConfigName+".toml")
		if err := mergeFile(cfg, projectPath); err != nil {
			return cfg, fmt.Errorf("project config error: %w", err)
		}
	}

	// Environment variable overrides
	prefix := l.opts.EnvPrefix
	if prefix == "" {
		prefix = strings.ToUpper(l.opts.AppName)
	}
	if err := applyEnvOverrides(cfg, prefix); err != nil {
		return cfg, fmt.Errorf("env override error: %w", err)
	}

	return cfg, nil
}

// mergeFile reads a TOML file and applies non-zero values to cfg using json tags.
// Missing files are silently skipped.
func mergeFile[T any](cfg *T, path string) error {
	if _, err := os.Stat(path); os.IsNotExist(err) {
		return nil
	}

	var raw map[string]interface{}
	if _, err := toml.DecodeFile(path, &raw); err != nil {
		return fmt.Errorf("failed to parse %s: %w", path, err)
	}

	if err := applyMapToStruct(reflect.ValueOf(cfg).Elem(), raw); err != nil {
		return fmt.Errorf("failed to apply %s: %w", path, err)
	}
	return nil
}

// walkStructFields iterates settable struct fields with json tags.
// For each field, fn is called with the field value and its json tag.
// This is the shared field-walking implementation for both TOML and env sources.
func walkStructFields(val reflect.Value, fn func(field reflect.Value, tag string) error) error {
	typ := val.Type()
	for i := 0; i < val.NumField(); i++ {
		field := val.Field(i)
		fieldType := typ.Field(i)

		if !field.CanSet() {
			continue
		}

		tag := jsonTag(fieldType)
		if tag == "" {
			continue
		}

		if err := fn(field, tag); err != nil {
			return err
		}
	}
	return nil
}

// applyMapToStruct applies values from a TOML-decoded map to a struct using json tags.
// Only non-zero values are applied (except pointer fields, which are set when present).
// A value whose type cannot be converted to the target field returns an error
// instead of being silently ignored.
func applyMapToStruct(val reflect.Value, raw map[string]interface{}) error {
	return walkStructFields(val, func(field reflect.Value, tag string) error {
		rawVal, ok := raw[tag]
		if !ok {
			return nil
		}

		switch field.Kind() {
		case reflect.Ptr:
			if rawVal == nil {
				return nil
			}
			ptrVal := reflect.New(field.Type().Elem())
			if err := setFieldValue(ptrVal.Elem(), rawVal); err != nil {
				return fmt.Errorf("field %q: %w", tag, err)
			}
			field.Set(ptrVal)
		case reflect.Struct:
			if subMap, ok := rawVal.(map[string]interface{}); ok {
				if err := applyMapToStruct(field, subMap); err != nil {
					return fmt.Errorf("field %q: %w", tag, err)
				}
			}
		default:
			if !isZeroInterface(rawVal) {
				if err := setFieldValue(field, rawVal); err != nil {
					return fmt.Errorf("field %q: %w", tag, err)
				}
			}
		}
		return nil
	})
}

// applyEnvOverrides sets struct fields from environment variables.
// Env var names follow the pattern {PREFIX}_{SECTION}_{FIELD} (uppercase).
// Pointer fields are allocated and set when the env var is present.
func applyEnvOverrides[T any](cfg *T, prefix string) error {
	return applyEnvToFields(reflect.ValueOf(cfg).Elem(), prefix)
}

func applyEnvToFields(val reflect.Value, prefix string) error {
	return walkStructFields(val, func(field reflect.Value, tag string) error {
		envKey := prefix + "_" + strings.ToUpper(tag)

		switch field.Kind() {
		case reflect.Ptr:
			if v := os.Getenv(envKey); v != "" {
				ptrVal := reflect.New(field.Type().Elem())
				if err := setFieldValue(ptrVal.Elem(), v); err != nil {
					return fmt.Errorf("env %s: %w", envKey, err)
				}
				field.Set(ptrVal)
			}
		case reflect.Struct:
			if err := applyEnvToFields(field, envKey); err != nil {
				return err
			}
		case reflect.Slice:
			// Env slices use comma-separated values, e.g. TAGS=web,api,production.
			if v := os.Getenv(envKey); v != "" {
				items := strings.Split(v, ",")
				for i := range items {
					items[i] = strings.TrimSpace(items[i])
				}
				if err := setFieldValue(field, items); err != nil {
					return fmt.Errorf("env %s: %w", envKey, err)
				}
			}
		case reflect.Map:
			// Not supported for env var overrides; skip silently.
		default:
			if v := os.Getenv(envKey); v != "" {
				if err := setFieldValue(field, v); err != nil {
					return fmt.Errorf("env %s: %w", envKey, err)
				}
			}
		}
		return nil
	})
}

func jsonTag(fieldType reflect.StructField) string {
	tag := fieldType.Tag.Get("json")
	if tag == "" || tag == "-" {
		return ""
	}
	if idx := strings.IndexByte(tag, ','); idx != -1 {
		tag = tag[:idx]
	}
	return tag
}

func isZeroInterface(v interface{}) bool {
	if v == nil {
		return true
	}
	switch val := v.(type) {
	case string:
		return val == ""
	case int64:
		return val == 0
	case float64:
		return val == 0
	case bool:
		return !val
	default:
		return false
	}
}

// setFieldValue sets a reflect.Value from a decoded TOML interface{} or env string value.
// This is the single shared conversion path for both TOML and env sources.
// The TOML source passes interface{} values directly from the decoder.
// The env source passes string values (or []string for comma-separated slices).
// Type support is identical across both sources: string, int*, uint*, float*,
// bool, time.Duration, slices ([]interface{} from TOML, []string from env),
// and maps (error).
func setFieldValue(field reflect.Value, raw interface{}) error {
	if raw == nil {
		return nil
	}

	// time.Duration is int64 under the hood; check type before the int64 case.
	if field.Type() == reflect.TypeOf(time.Duration(0)) {
		switch v := raw.(type) {
		case string:
			d, err := time.ParseDuration(v)
			if err != nil {
				return fmt.Errorf("cannot parse %q as duration: %w", v, err)
			}
			field.SetInt(int64(d))
			return nil
		case int64:
			field.SetInt(v)
			return nil
		default:
			return fmt.Errorf("cannot convert %T to duration", raw)
		}
	}

	switch field.Kind() {
	case reflect.String:
		s, ok := raw.(string)
		if !ok {
			return fmt.Errorf("cannot convert %T to string", raw)
		}
		field.SetString(s)
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		switch v := raw.(type) {
		case int64:
			field.SetInt(v)
		case int:
			field.SetInt(int64(v))
		case float64:
			field.SetInt(int64(v))
		case string:
			n, err := strconv.ParseInt(v, 10, 64)
			if err != nil {
				return fmt.Errorf("cannot parse %q as int: %w", v, err)
			}
			field.SetInt(n)
		default:
			return fmt.Errorf("cannot convert %T to int", raw)
		}
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		switch v := raw.(type) {
		case int64:
			if v < 0 {
				return fmt.Errorf("cannot convert negative value %d to uint", v)
			}
			field.SetUint(uint64(v))
		case float64:
			if v < 0 {
				return fmt.Errorf("cannot convert negative value %v to uint", v)
			}
			field.SetUint(uint64(v))
		case string:
			n, err := strconv.ParseUint(v, 10, 64)
			if err != nil {
				return fmt.Errorf("cannot parse %q as uint: %w", v, err)
			}
			field.SetUint(n)
		default:
			return fmt.Errorf("cannot convert %T to uint", raw)
		}
	case reflect.Float32, reflect.Float64:
		switch v := raw.(type) {
		case float64:
			field.SetFloat(v)
		case int64:
			field.SetFloat(float64(v))
		case string:
			n, err := strconv.ParseFloat(v, 64)
			if err != nil {
				return fmt.Errorf("cannot parse %q as float: %w", v, err)
			}
			field.SetFloat(n)
		default:
			return fmt.Errorf("cannot convert %T to float", raw)
		}
	case reflect.Bool:
		switch v := raw.(type) {
		case bool:
			field.SetBool(v)
		case string:
			b, err := strconv.ParseBool(v)
			if err != nil {
				return fmt.Errorf("cannot parse %q as bool: %w", v, err)
			}
			field.SetBool(b)
		default:
			return fmt.Errorf("cannot convert %T to bool", raw)
		}
	case reflect.Slice:
		switch v := raw.(type) {
		case []interface{}:
			// From TOML: array of decoded values.
			slice := reflect.MakeSlice(field.Type(), len(v), len(v))
			for i, item := range v {
				if err := setFieldValue(slice.Index(i), item); err != nil {
					return fmt.Errorf("slice element %d: %w", i, err)
				}
			}
			field.Set(slice)
		case []string:
			// From env: comma-separated string values.
			slice := reflect.MakeSlice(field.Type(), len(v), len(v))
			for i, item := range v {
				if err := setFieldValue(slice.Index(i), item); err != nil {
					return fmt.Errorf("slice element %d: %w", i, err)
				}
			}
			field.Set(slice)
		default:
			return fmt.Errorf("cannot convert %T to %s", raw, field.Type())
		}
	case reflect.Map:
		return fmt.Errorf("map fields are not supported from config")
	default:
		return fmt.Errorf("unsupported field kind %s", field.Kind())
	}
	return nil
}
