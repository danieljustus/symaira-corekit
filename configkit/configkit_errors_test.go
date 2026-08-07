package configkit

import (
	"reflect"
	"strings"
	"testing"
	"time"
)

// TestSetFieldValueErrors exercises the type-conversion error branches of the
// shared TOML/env conversion path (setFieldValue). These branches are the
// reason configkit sat below the default 80% coverage bar.
func TestSetFieldValueErrors(t *testing.T) {
	// time.Duration parse failure.
	var durField time.Duration
	if err := setFieldValue(reflect.ValueOf(&durField).Elem(), "not-a-duration"); err == nil {
		t.Error("duration parse failure should error")
	} else if !strings.Contains(err.Error(), "duration") {
		t.Errorf("duration error = %q, want mention of duration", err.Error())
	}

	// time.Duration from unsupported type.
	if err := setFieldValue(reflect.ValueOf(&durField).Elem(), true); err == nil {
		t.Error("duration from bool should error")
	}

	// int from unsupported type.
	var intField int
	if err := setFieldValue(reflect.ValueOf(&intField).Elem(), true); err == nil {
		t.Error("int from bool should error")
	}

	// int from unparseable string.
	if err := setFieldValue(reflect.ValueOf(&intField).Elem(), "abc"); err == nil {
		t.Error("int from bad string should error")
	}

	// uint from negative value.
	var uintField uint
	if err := setFieldValue(reflect.ValueOf(&uintField).Elem(), int64(-5)); err == nil {
		t.Error("uint from negative int64 should error")
	}

	// uint from negative float.
	if err := setFieldValue(reflect.ValueOf(&uintField).Elem(), float64(-1.5)); err == nil {
		t.Error("uint from negative float should error")
	}

	// uint from unparseable string.
	if err := setFieldValue(reflect.ValueOf(&uintField).Elem(), "xyz"); err == nil {
		t.Error("uint from bad string should error")
	}

	// uint from unsupported type.
	if err := setFieldValue(reflect.ValueOf(&uintField).Elem(), true); err == nil {
		t.Error("uint from bool should error")
	}

	// float from unsupported type.
	var floatField float64
	if err := setFieldValue(reflect.ValueOf(&floatField).Elem(), true); err == nil {
		t.Error("float from bool should error")
	}

	// float from unparseable string.
	if err := setFieldValue(reflect.ValueOf(&floatField).Elem(), "abc"); err == nil {
		t.Error("float from bad string should error")
	}

	// bool from unparseable string.
	var boolField bool
	if err := setFieldValue(reflect.ValueOf(&boolField).Elem(), "maybe"); err == nil {
		t.Error("bool from bad string should error")
	}

	// bool from unsupported type.
	if err := setFieldValue(reflect.ValueOf(&boolField).Elem(), 42); err == nil {
		t.Error("bool from int should error")
	}

	// slice from unsupported type.
	var sliceField []string
	if err := setFieldValue(reflect.ValueOf(&sliceField).Elem(), 42); err == nil {
		t.Error("slice from int should error")
	}

	// slice element type mismatch ([]string from []interface{}{42}).
	if err := setFieldValue(reflect.ValueOf(&sliceField).Elem(), []interface{}{42}); err == nil {
		t.Error("slice element type mismatch should error")
	}

	// map fields are rejected from config.
	var mapField map[string]int
	if err := setFieldValue(reflect.ValueOf(&mapField).Elem(), map[string]interface{}{"a": 1}); err == nil {
		t.Error("map field should error")
	}

	// unsupported field kind (chan).
	var chanField chan int
	if err := setFieldValue(reflect.ValueOf(&chanField).Elem(), 1); err == nil {
		t.Error("chan field should error")
	}
}

// TestJsonTagEdgeCases covers the tag-normalization branches of jsonTag.
func TestJsonTagEdgeCases(t *testing.T) {
	type withTags struct {
		NoTag      string
		Omit       string `json:"-"`
		WithOption string `json:"name,omitempty"`
	}

	rt := reflect.TypeOf(withTags{})
	if got := jsonTag(rt.Field(0)); got != "" {
		t.Errorf("jsonTag(no tag) = %q, want empty", got)
	}
	if got := jsonTag(rt.Field(1)); got != "" {
		t.Errorf("jsonTag(-) = %q, want empty", got)
	}
	if got := jsonTag(rt.Field(2)); got != "name" {
		t.Errorf("jsonTag(name,omitempty) = %q, want name", got)
	}
}

// TestReloadRefreshesConfig covers the Reload path, which was at 0%.
func TestReloadRefreshesConfig(t *testing.T) {
	loader := NewLoader(Options{AppName: "reloadapp"}, func() *testConfig { return testDefaults() })

	first, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	// Reload must return a fresh value and not error. loadOnce always
	// allocates a new config from defaults, so the pointer must differ
	// from the cached one.
	second, err := loader.Reload()
	if err != nil {
		t.Fatalf("Reload() error = %v", err)
	}
	if first == second {
		t.Error("Reload returned the cached pointer; expected a fresh load")
	}
	if second.Timeout != 30 {
		t.Errorf("Reload Timeout = %d, want default 30", second.Timeout)
	}

	// ResetCache must make the next Load re-read from defaults.
	loader.ResetCache()
	third, err := loader.Load()
	if err != nil {
		t.Fatalf("Load() after ResetCache error = %v", err)
	}
	if third == second {
		t.Error("Load after ResetCache returned the cached pointer; expected re-read")
	}
}
