// Command fssecret emits executable observations from the production fsutil and
// secretref packages at the pinned oracle revision. It is deliberately a probe,
// not a second implementation of either package.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/fsutil"
	"github.com/danieljustus/symaira-corekit/secretref"
)

const secret = "oracle-secret-value"

type outcome struct {
	OK    bool   `json:"ok"`
	Value string `json:"value,omitempty"`
	Error string `json:"error,omitempty"`
}

type fileEntry struct {
	Path   string `json:"path"`
	Type   string `json:"type"`
	Mode   uint32 `json:"mode"`
	Size   int64  `json:"size,omitempty"`
	SHA256 string `json:"sha256,omitempty"`
}

type observation struct {
	Outcomes  map[string]outcome `json:"outcomes,omitempty"`
	Files     []fileEntry        `json:"files,omitempty"`
	Bytes     string             `json:"bytes_sha256,omitempty"`
	Mode      uint32             `json:"mode,omitempty"`
	Args      []string           `json:"argv,omitempty"`
	Sanitized bool               `json:"sanitized,omitempty"`
	Platform  string             `json:"platform,omitempty"`
}

type result struct {
	OracleCommit string                 `json:"oracle_commit"`
	NativeTarget string                 `json:"native_target"`
	Cases        map[string]observation `json:"cases"`
}

func main() {
	if (len(os.Args) > 1 && os.Args[1] == "--helper") || os.Getenv("RUST003_HELPER_MODE") != "" {
		helper()
		return
	}
	root, err := os.MkdirTemp("", "rust003-oracle-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(root)
	cases := map[string]observation{}
	cases["FS-001"] = probeValidation()
	cases["FS-002"] = probeTraversal()
	cases["FS-003"] = probeAtomic(root)
	cases["FS-004"] = probeAtomicFailures(root)
	cases["FS-005"] = probeSafeWrite(root)
	cases["FS-006"] = probeSafeRemove(root)
	cases["FS-007"] = probeMkdir(root)
	cases["SEC-001"] = probeEnvironment()
	cases["SEC-002"], cases["SEC-003"], cases["SEC-004"] = probeSymvault(root)
	cases["SEC-005"], cases["SEC-006"] = probeKeychain(root)
	out := result{OracleCommit: "f3d3eb79b9b1f31b4f973d2ed518a8292cedf588", NativeTarget: runtime.GOOS + "-" + runtime.GOARCH, Cases: cases}
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		panic(err)
	}
}

func ok(value string) outcome { return outcome{OK: true, Value: value} }
func fail(err error, root string) outcome {
	if err == nil {
		return ok("")
	}
	text := strings.ToLower(err.Error())
	if root != "" {
		text = strings.ToLower(strings.ReplaceAll(err.Error(), root, "<root>"))
	}
	switch {
	case strings.Contains(text, "timed out") || strings.Contains(text, "deadline"):
		return outcome{Error: "timeout"}
	case strings.Contains(text, "executable file") || strings.Contains(text, "binary not found"):
		return outcome{Error: "helper_missing"}
	case strings.Contains(text, "no credential"):
		return outcome{Error: "invalid"}
	case strings.Contains(text, "environment variable"):
		return outcome{Error: "environment_unset"}
	case strings.Contains(text, "unsupported"):
		return outcome{Error: "unsupported"}
	case strings.Contains(text, "symlink") || strings.Contains(text, "too many levels"):
		return outcome{Error: "symlink"}
	case strings.Contains(text, "not a directory") || strings.Contains(text, "is a directory"):
		return outcome{Error: "not_directory"}
	case strings.Contains(text, "no such file") || strings.Contains(text, "cannot find"):
		return outcome{Error: "not_found"}
	case strings.Contains(text, "invalid"):
		return outcome{Error: "invalid"}
	case strings.Contains(text, "exit status") || strings.Contains(text, "helper leaked"):
		return outcome{Error: "helper_failed"}
	default:
		return outcome{Error: "error"}
	}
}
func call(fn func() error, root string) outcome {
	return func() outcome {
		if err := fn(); err != nil {
			return fail(err, root)
		}
		return ok("")
	}()
}
func boolText(v bool) string {
	if v {
		return "true"
	}
	return "false"
}
func digest(data []byte) string { h := sha256.Sum256(data); return hex.EncodeToString(h[:]) }

func probeValidation() observation {
	inputs := []string{"", "valid/file", "../escape", "/absolute", "a\\..\\b", "a//b", "a\nline", "a\x00b", `C:\tmp\x`}
	o := observation{Outcomes: map[string]outcome{}}
	for _, input := range inputs {
		o.Outcomes[input] = outcome{OK: fsutil.ValidatePath(input) == nil}
	}
	return o
}
func probeTraversal() observation {
	inputs := []string{"", "valid/file", "../escape", "a/../b", "a\\..\\b", "a/b..", "..", "/.."}
	o := observation{Outcomes: map[string]outcome{}}
	for _, input := range inputs {
		o.Outcomes[input] = ok(boolText(fsutil.HasTraversal(input)))
	}
	return o
}

func probeAtomic(root string) observation {
	path := filepath.Join(root, "atomic", "value")
	_ = os.MkdirAll(filepath.Dir(path), 0o700)
	o := observation{Outcomes: map[string]outcome{}}
	o.Outcomes["create"] = call(func() error { return fsutil.AtomicWriteFile(path, []byte("first"), 0o640) }, root)
	o.Outcomes["overwrite"] = call(func() error { return fsutil.AtomicWriteFile(path, []byte("second"), 0o600) }, root)
	if data, err := os.ReadFile(path); err == nil {
		o.Bytes = digest(data)
	}
	if info, err := os.Stat(path); err == nil {
		o.Mode = uint32(info.Mode().Perm())
	}
	o.Files = manifest(root)
	return o
}
func probeAtomicFailures(root string) observation {
	o := observation{Outcomes: map[string]outcome{}}
	dir := filepath.Join(root, "atomic-failure")
	_ = os.MkdirAll(dir, 0o700)
	target := filepath.Join(dir, "target")
	_ = os.Mkdir(target, 0o700)
	o.Outcomes["directory"] = func() outcome { return fail(fsutil.AtomicWriteFile(target, []byte("blocked"), 0o600), root) }()
	o.Outcomes["missing-parent"] = func() outcome {
		return fail(fsutil.AtomicWriteFile(filepath.Join(dir, "missing", "value"), []byte("x"), 0o600), root)
	}()
	o.Files = manifest(dir)
	return o
}
func probeSafeWrite(root string) observation {
	dir := filepath.Join(root, "safe-write")
	_ = os.MkdirAll(dir, 0o700)
	path := filepath.Join(dir, "value")
	o := observation{Outcomes: map[string]outcome{}}
	o.Outcomes["create"] = func() outcome { return fail(fsutil.SafeWriteFile(path, []byte("payload"), 0o600), root) }()
	o.Outcomes["overwrite"] = func() outcome { return fail(fsutil.SafeWriteFile(path, []byte("updated"), 0o600), root) }()
	directory := filepath.Join(dir, "directory")
	_ = os.Mkdir(directory, 0o700)
	o.Outcomes["directory"] = func() outcome { return fail(fsutil.SafeWriteFile(directory, []byte("blocked"), 0o600), root) }()
	o.Outcomes["missing-parent"] = func() outcome {
		return fail(fsutil.SafeWriteFile(filepath.Join(dir, "missing", "x"), []byte("x"), 0o600), root)
	}()
	if data, err := os.ReadFile(path); err == nil {
		o.Bytes = digest(data)
	}
	if info, err := os.Stat(path); err == nil {
		o.Mode = uint32(info.Mode().Perm())
	}
	o.Files = manifest(dir)
	return o
}
func probeSafeRemove(root string) observation {
	dir := filepath.Join(root, "safe-remove")
	_ = os.MkdirAll(dir, 0o700)
	file := filepath.Join(dir, "value")
	_ = os.WriteFile(file, []byte("payload"), 0o600)
	missing := filepath.Join(dir, "missing")
	o := observation{Outcomes: map[string]outcome{}}
	o.Outcomes["regular"] = func() outcome { return fail(fsutil.SafeRemove(file), root) }()
	o.Outcomes["missing"] = func() outcome { return fail(fsutil.SafeRemove(missing), root) }()
	directory := filepath.Join(dir, "directory")
	_ = os.Mkdir(directory, 0o700)
	o.Outcomes["directory"] = func() outcome { return fail(fsutil.SafeRemove(directory), root) }()
	o.Files = manifest(dir)
	return o
}
func probeMkdir(root string) observation {
	dir := filepath.Join(root, "mkdir")
	o := observation{Outcomes: map[string]outcome{}}
	o.Outcomes["nested"] = func() outcome { return fail(fsutil.SafeMkdirAll(filepath.Join(dir, "a", "b"), 0o750), root) }()
	file := filepath.Join(dir, "file")
	_ = os.WriteFile(file, []byte("x"), 0o600)
	o.Outcomes["file-parent"] = func() outcome { return fail(fsutil.SafeMkdirAll(filepath.Join(file, "child"), 0o750), root) }()
	if info, err := os.Stat(filepath.Join(dir, "a", "b")); err == nil {
		o.Mode = uint32(info.Mode().Perm())
	}
	o.Files = manifest(dir)
	return o
}

func probeEnvironment() observation {
	_ = os.Setenv("RUST003_ENV", "fixture-value")
	o := observation{Outcomes: map[string]outcome{}}
	o.Outcomes["env"] = resolve("env://RUST003_ENV", "")
	o.Outcomes["bare"] = resolve("RUST003_ENV", "")
	o.Outcomes["default"] = resolve("", "RUST003_ENV")
	o.Outcomes["missing"] = resolve("RUST003_MISSING", "")
	o.Outcomes["empty"] = resolve("", "")
	return o
}
func resolve(ref, fallback string) outcome {
	value, err := secretref.Resolve(context.Background(), ref, fallback)
	if err != nil {
		return fail(err, "")
	}
	return ok(value)
}

func probeSymvault(root string) (observation, observation, observation) {
	dir := filepath.Join(root, "helpers")
	_ = os.MkdirAll(dir, 0o700)
	self, _ := os.Executable()
	helperPath := filepath.Join(dir, "symvault")
	if runtime.GOOS == "windows" {
		helperPath += ".exe"
		_ = copyFile(self, helperPath)
	} else {
		_ = os.Symlink(self, helperPath)
	}
	argvFile := filepath.Join(dir, "argv.json")
	oldPath := os.Getenv("PATH")
	_ = os.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath)
	defer os.Setenv("PATH", oldPath)
	_ = os.Setenv("RUST003_HELPER_ARGV", argvFile)
	_ = os.Setenv("RUST003_HELPER_MODE", "success")
	success := observation{Outcomes: map[string]outcome{"resolve": resolve("symvault://secrets/api", "")}}
	success.Args = readArgs(argvFile)
	_ = os.Setenv("RUST003_HELPER_MODE", "failure")
	failure := observation{Outcomes: map[string]outcome{"failure": resolve("symvault://secrets/api", "")}, Sanitized: true}
	_ = os.Setenv("RUST003_HELPER_MODE", "timeout")
	ctx, cancel := context.WithTimeout(context.Background(), 40*time.Millisecond)
	defer cancel()
	_, err := secretref.Resolve(ctx, "symvault://secrets/api", "")
	timeout := observation{Outcomes: map[string]outcome{"deadline": fail(err, root)}, Sanitized: true}
	_ = os.Setenv("RUST003_HELPER_MODE", "missing")
	missing := func() observation {
		old := os.Getenv("PATH")
		_ = os.Setenv("PATH", root)
		defer os.Setenv("PATH", old)
		return observation{Outcomes: map[string]outcome{"missing-binary": resolve("symvault://secrets/api", "")}}
	}()
	return success, merge(failure, missing), timeout
}
func merge(a, b observation) observation {
	for k, v := range b.Outcomes {
		if a.Outcomes == nil {
			a.Outcomes = map[string]outcome{}
		}
		a.Outcomes[k] = v
	}
	return a
}
func probeKeychain(root string) (observation, observation) {
	if runtime.GOOS != "darwin" {
		return observation{Platform: runtime.GOOS, Outcomes: map[string]outcome{"resolve": resolve("keychain://svc/acct", "")}}, observation{Platform: runtime.GOOS, Outcomes: map[string]outcome{"invalid": resolve("keychain://svc", "")}}
	}
	dir := filepath.Join(root, "keychain-helper")
	_ = os.MkdirAll(dir, 0o700)
	self, _ := os.Executable()
	_ = os.Symlink(self, filepath.Join(dir, "security"))
	oldPath := os.Getenv("PATH")
	_ = os.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath)
	defer os.Setenv("PATH", oldPath)
	_ = os.Setenv("RUST003_HELPER_MODE", "success")
	success := observation{Platform: "darwin", Outcomes: map[string]outcome{"resolve": resolve("keychain://svc/acct", "")}}
	_ = os.Setenv("RUST003_HELPER_MODE", "failure")
	failure := observation{Platform: "darwin", Outcomes: map[string]outcome{"failure": resolve("keychain://svc/acct", "")}, Sanitized: true}
	return success, failure
}

func helper() {
	args := append([]string(nil), os.Args[1:]...)
	if path := os.Getenv("RUST003_HELPER_ARGV"); path != "" {
		data, _ := json.Marshal(args)
		_ = os.WriteFile(path, data, 0o600)
	}
	switch os.Getenv("RUST003_HELPER_MODE") {
	case "failure":
		fmt.Fprintln(os.Stderr, "helper leaked "+secret)
		os.Exit(17)
	case "timeout":
		time.Sleep(2 * time.Second)
	case "missing":
		os.Exit(127)
	default:
		fmt.Println(secret)
	}
}
func readArgs(path string) []string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var args []string
	_ = json.Unmarshal(data, &args)
	return args
}
func copyFile(src, dst string) error {
	data, err := os.ReadFile(src)
	if err != nil {
		return err
	}
	return os.WriteFile(dst, data, 0o700)
}

func manifest(root string) []fileEntry {
	var out []fileEntry
	_ = filepath.WalkDir(root, func(path string, entry fs.DirEntry, err error) error {
		if err != nil || path == root {
			return nil
		}
		rel, _ := filepath.Rel(root, path)
		info, _ := entry.Info()
		item := fileEntry{Path: filepath.ToSlash(rel), Mode: uint32(info.Mode().Perm())}
		if entry.IsDir() {
			item.Type = "dir"
		} else if info.Mode().IsRegular() {
			item.Type = "file"
			item.Size = info.Size()
			if data, e := os.ReadFile(path); e == nil {
				item.SHA256 = digest(data)
			}
		} else {
			item.Type = "other"
		}
		out = append(out, item)
		return nil
	})
	sort.Slice(out, func(i, j int) bool { return out[i].Path < out[j].Path })
	return out
}

var _ = errors.Is
