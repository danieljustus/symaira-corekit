package mcpcfgkit

import (
	"fmt"

	"gopkg.in/yaml.v3"
)

// yamlUnmarshal is a thin wrapper so discovery.go stays readable and the
// yaml.v3 dependency is contained to this file.
func yamlUnmarshal(data []byte, out any) error {
	return yaml.Unmarshal(data, out)
}

// entryFromYAML converts a YAML server entry (map[string]any) into Entry.
func entryFromYAML(v any) (Entry, error) {
	m, ok := v.(map[string]any)
	if !ok {
		return Entry{}, fmt.Errorf("entry is not an object")
	}
	e := Entry{}
	if cmd, ok := m["command"].(string); ok {
		e.Command = cmd
	}
	if args, ok := m["args"].([]any); ok {
		for _, a := range args {
			if s, ok := a.(string); ok {
				e.Args = append(e.Args, s)
			}
		}
	}
	if u, ok := m["url"].(string); ok {
		e.URL = u
	}
	if t, ok := m["type"].(string); ok {
		e.Type = t
	}
	if t, ok := m["transport"].(string); ok {
		e.Transport = t
	}
	if env, ok := m["env"].(map[string]any); ok {
		e.Env = make(map[string]string, len(env))
		for k, v := range env {
			if s, ok := v.(string); ok {
				e.Env[k] = s
			}
		}
	}
	return e, nil
}
