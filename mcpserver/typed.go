package mcpserver

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
)

// RegisterTyped registers a tool whose input schema is derived from the Go
// type T and whose handler receives the raw "arguments" object unmarshalled
// into T. It is an additive convenience over the raw Tool{InputSchema,
// Handler} path, which keeps working unchanged.
//
// Schema derivation rules:
//   - T must be a struct (or a pointer to a struct); the resulting schema is
//     always of type "object".
//   - Field names come from the `json` tag (the part before the first comma),
//     falling back to the field name. Fields tagged `json:"-"` and unexported
//     fields are skipped.
//   - A `desc` tag provides the property's "description".
//   - A field is "required" unless it is a pointer type or its json tag
//     carries `omitempty`.
//   - Supported field kinds: string, bool, all int/uint sizes (integer),
//     float32/float64 (number), slices (array, item schema derived
//     recursively), nested structs and pointers to structs (object), and
//     json.RawMessage (opaque). Unsupported kinds cause RegisterTyped to
//     panic, mirroring RegisterTool's panic-on-misuse contract.
//
// Dispatch policy: arguments are decoded with DisallowUnknownFields, so
// clients sending properties outside the derived schema get a descriptive
// tool error instead of silently dropped data. Bad JSON is likewise reported
// as a tool error.
func RegisterTyped[T any](srv *Server, name, description string, handler func(context.Context, T) (any, error)) {
	if srv == nil {
		panic("mcpserver: RegisterTyped called with nil Server")
	}
	if handler == nil {
		panic("mcpserver: RegisterTyped called with nil handler")
	}

	t := reflect.TypeOf((*T)(nil)).Elem()
	schema, err := objectSchemaFor(t)
	if err != nil {
		panic(fmt.Sprintf("mcpserver: RegisterTyped(%s): %v", name, err))
	}
	raw, err := json.Marshal(schema)
	if err != nil {
		panic(fmt.Sprintf("mcpserver: RegisterTyped(%s): marshal schema: %v", name, err))
	}

	srv.RegisterTool(&Tool{
		Name:        name,
		Description: description,
		InputSchema: raw,
		Handler: func(ctx context.Context, input json.RawMessage) (any, error) {
			var args T
			if len(input) == 0 {
				input = json.RawMessage(`{}`)
			}
			dec := json.NewDecoder(bytes.NewReader(input))
			dec.DisallowUnknownFields()
			if err := dec.Decode(&args); err != nil {
				return nil, fmt.Errorf("invalid arguments for %s: %w", name, err)
			}
			return handler(ctx, args)
		},
	})
}

// objectSchemaFor builds an object-type JSON Schema for a struct type.
func objectSchemaFor(t reflect.Type) (map[string]any, error) {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	if t.Kind() != reflect.Struct {
		return nil, fmt.Errorf("type %s is not a struct", t)
	}

	properties := map[string]any{}
	var required []string
	for i := 0; i < t.NumField(); i++ {
		f := t.Field(i)
		if !f.IsExported() {
			continue
		}
		name, optional, skip := jsonFieldName(f)
		if skip {
			continue
		}
		prop, err := schemaFor(f.Type)
		if err != nil {
			return nil, fmt.Errorf("field %s: %w", f.Name, err)
		}
		if desc, ok := f.Tag.Lookup("desc"); ok && desc != "" {
			prop["description"] = desc
		}
		properties[name] = prop
		if !optional {
			required = append(required, name)
		}
	}

	schema := map[string]any{
		"type":       "object",
		"properties": properties,
	}
	if len(required) > 0 {
		schema["required"] = required
	}
	return schema, nil
}

// schemaFor builds the property schema for a single field type.
func schemaFor(t reflect.Type) (map[string]any, error) {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	switch t.Kind() {
	case reflect.String:
		return map[string]any{"type": "string"}, nil
	case reflect.Bool:
		return map[string]any{"type": "boolean"}, nil
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return map[string]any{"type": "integer"}, nil
	case reflect.Float32, reflect.Float64:
		return map[string]any{"type": "number"}, nil
	case reflect.Slice:
		if t.Elem().Kind() == reflect.Uint8 {
			// []byte is JSON-encoded as base64 string.
			return map[string]any{"type": "string"}, nil
		}
		items, err := schemaFor(t.Elem())
		if err != nil {
			return nil, err
		}
		return map[string]any{"type": "array", "items": items}, nil
	case reflect.Struct:
		if t == reflect.TypeOf(json.RawMessage{}) {
			return map[string]any{}, nil
		}
		return objectSchemaFor(t)
	default:
		return nil, fmt.Errorf("unsupported field kind %s", t.Kind())
	}
}

// jsonFieldName resolves the schema property name and optionality of a struct
// field from its json tag.
func jsonFieldName(f reflect.StructField) (name string, optional, skip bool) {
	optional = f.Type.Kind() == reflect.Pointer
	tag, ok := f.Tag.Lookup("json")
	if !ok {
		return f.Name, optional, false
	}
	parts := strings.Split(tag, ",")
	if parts[0] == "-" {
		return "", false, true
	}
	if parts[0] != "" {
		name = parts[0]
	} else {
		name = f.Name
	}
	for _, opt := range parts[1:] {
		if opt == "omitempty" {
			optional = true
		}
	}
	return name, optional, false
}
