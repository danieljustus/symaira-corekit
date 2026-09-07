// Command probe emits deterministic production CoreKit behavior for harness self-tests.
package main

import (
	"encoding/json"
	"fmt"
	"os"

	"github.com/danieljustus/symaira-corekit/envutil"
	"github.com/danieljustus/symaira-corekit/exitcodes"
	"github.com/danieljustus/symaira-corekit/fsutil"
	"github.com/danieljustus/symaira-corekit/versionkit"
)

type request struct {
	Tool          string   `json:"tool"`
	Version       string   `json:"version"`
	SchemaVersion int      `json:"schema_version"`
	EnvName       string   `json:"env_name"`
	EnvAliases    []string `json:"env_aliases"`
	OutputPath    string   `json:"output_path"`
}

type response struct {
	VersionJSON string         `json:"version_json"`
	VersionText string         `json:"version_text"`
	EnvValue    string         `json:"env_value"`
	ExitCodes   map[string]int `json:"exit_codes"`
	ProcessArgv []string       `json:"process_argv"`
	HTTPTrace   []string       `json:"http_transcript"`
}

func main() {
	var input request
	if err := json.NewDecoder(os.Stdin).Decode(&input); err != nil {
		fatal("decode input: %v", err)
	}
	info := versionkit.New(input.Tool, input.Version, input.SchemaVersion)
	versionJSON, err := info.JSON()
	if err != nil {
		fatal("encode version: %v", err)
	}
	if input.OutputPath != "" {
		if err := fsutil.AtomicWriteFile(input.OutputPath, append(versionJSON, '\n'), 0o600); err != nil {
			fatal("write output: %v", err)
		}
	}
	out := response{
		VersionJSON: string(versionJSON),
		VersionText: info.String(),
		EnvValue:    envutil.Getenv(input.EnvName, input.EnvAliases...),
		ExitCodes: map[string]int{
			"ok": int(exitcodes.ExitOK), "generic": int(exitcodes.ExitGeneric),
			"no_input": int(exitcodes.ExitNoInput), "no_auth": int(exitcodes.ExitNoAuth),
			"forbidden": int(exitcodes.ExitForbidden), "not_found": int(exitcodes.ExitNotFound),
			"conflict": int(exitcodes.ExitConflict), "software": int(exitcodes.ExitSoftware),
			"data": int(exitcodes.ExitData), "config": int(exitcodes.ExitConfig),
			"interrupted": int(exitcodes.ExitInterrupted),
		},
		ProcessArgv: []string{},
		HTTPTrace:   []string{},
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(out); err != nil {
		fatal("encode output: %v", err)
	}
}

func fatal(format string, args ...any) {
	_, _ = fmt.Fprintf(os.Stderr, "probe: "+format+"\n", args...)
	os.Exit(1)
}
