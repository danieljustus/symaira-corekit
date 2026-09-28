// Command update-apply-oracle observes updatecheck/updateapply through its exported API.
package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"time"

	"github.com/danieljustus/symaira-corekit/updatecheck"
	"github.com/danieljustus/symaira-corekit/updatecheck/updateapply"
)

type input struct {
	ID             string `json:"id"`
	AssetName      string `json:"asset_name"`
	PayloadHex     string `json:"payload_hex"`
	ChecksumOK     bool   `json:"checksum_ok"`
	InitialExists  bool   `json:"initial_exists"`
	InitialContent string `json:"initial_content"`
	InitialMode    uint32 `json:"initial_mode"`
	ExtractBinary  string `json:"extract_binary,omitempty"`
	ValidateError  string `json:"validate_error,omitempty"`
	UseZip         bool   `json:"use_zip,omitempty"`
	OmitAsset      bool   `json:"omit_asset,omitempty"`
	BlockedParent  bool   `json:"blocked_parent,omitempty"`
	NestedParent   bool   `json:"nested_parent,omitempty"`
}

type file struct {
	Path    string `json:"path"`
	Content string `json:"content"`
	Mode    uint32 `json:"mode"`
}

type observation struct {
	ErrorCode              string `json:"error_code,omitempty"`
	TargetExists           bool   `json:"target_exists"`
	TargetContent          string `json:"target_content,omitempty"`
	TargetMode             uint32 `json:"target_mode,omitempty"`
	BackupExists           bool   `json:"backup_exists"`
	StageDuringDownload    bool   `json:"stage_during_download"`
	TempDuringDownload     bool   `json:"temp_during_download"`
	ValidatorSawTarget     bool   `json:"validator_saw_target"`
	ValidatorSawBackup     bool   `json:"validator_saw_backup"`
	ValidatorTargetContent string `json:"validator_target_content,omitempty"`
	Files                  []file `json:"files"`
}

type result struct {
	Input       input       `json:"input"`
	Observation observation `json:"observation"`
}

func main() {
	cases := []input{
		{ID: "install", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("new-binary")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755},
		{ID: "checksum-abort", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("new-binary")), ChecksumOK: false, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755},
		{ID: "validation-rollback", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("invalid-binary")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o640, ValidateError: "installed binary does not start"},
		{ID: "validation-first-install", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("invalid-binary")), ChecksumOK: true, ValidateError: "installed binary does not start"},
		{ID: "tar-extract", AssetName: "mytool_linux_amd64.tar.gz", PayloadHex: hex.EncodeToString(tarGz("bundle/mytool", "archive-binary")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755, ExtractBinary: "mytool"},
		{ID: "tar-traversal", AssetName: "mytool_linux_amd64.tar.gz", PayloadHex: hex.EncodeToString(tarGz("../mytool", "escaped")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755, ExtractBinary: "mytool"},
		{ID: "missing-asset", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("new-binary")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755, OmitAsset: true},
		{ID: "blocked-parent", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("new-binary")), ChecksumOK: true, BlockedParent: true},
		{ID: "nested-install", AssetName: "mytool_linux_amd64", PayloadHex: hex.EncodeToString([]byte("new-binary")), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755, NestedParent: true},
	}
	zipPath := filepath.Join("scripts", "rust-port", "update-extract-oracle", "testdata", "zip-success.zip")
	if archive, err := os.ReadFile(zipPath); err == nil { //nolint:gosec // path is built from this repository's own fixture table
		cases = append(cases, input{ID: "zip-extract-blocked", AssetName: "mytool_windows_amd64.zip", PayloadHex: hex.EncodeToString(archive), ChecksumOK: true, InitialExists: true, InitialContent: "old-binary", InitialMode: 0o755, ExtractBinary: "tool.exe", UseZip: true})
	}
	results := make([]result, 0, len(cases))
	for _, test := range cases {
		results = append(results, run(test))
	}
	if err := json.NewEncoder(os.Stdout).Encode(results); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(test input) result {
	payload, err := hex.DecodeString(test.PayloadHex)
	if err != nil {
		panic(err)
	}
	checksummed := payload
	if !test.ChecksumOK {
		checksummed = []byte("different payload")
	}
	checksums := fmt.Sprintf("%x  %s\n", sha256.Sum256(checksummed), test.AssetName)
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/checksums") {
			_, _ = w.Write([]byte(checksums))
			return
		}
		if !test.OmitAsset {
			_, _ = w.Write(payload)
		}
	})
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		panic(err)
	}
	server := &httptest.Server{Config: &http.Server{Handler: handler, ReadHeaderTimeout: 5 * time.Second}, Listener: listener}
	server.Start()
	defer server.Close()

	root, err := os.MkdirTemp("", "update-apply-oracle-")
	if err != nil {
		panic(err)
	}
	defer os.RemoveAll(root)
	target := filepath.Join(root, "mytool")
	if test.BlockedParent {
		parent := filepath.Join(root, "blocked-parent")
		if err := os.WriteFile(parent, []byte("blocker"), 0o600); err != nil { //nolint:gosec // isolated fixture root
			panic(err)
		}
		target = filepath.Join(parent, "mytool")
	}
	if test.NestedParent {
		parent := filepath.Join(root, "nested")
		if err := os.Mkdir(parent, 0o700); err != nil {
			panic(err)
		}
		target = filepath.Join(parent, "mytool")
	}
	if test.InitialExists {
		if err := os.WriteFile(target, []byte(test.InitialContent), os.FileMode(test.InitialMode)); err != nil {
			panic(err)
		}
	}
	if test.OmitAsset {
		// A missing matching asset is rejected before either URL is requested.
		test.AssetName = "other_darwin_arm64"
	}
	assets := []updatecheck.Asset{
		{Name: test.AssetName, BrowserDownloadURL: server.URL + "/asset"},
		{Name: "checksums.txt", BrowserDownloadURL: server.URL + "/checksums"},
	}
	var seenStage, seenTemp bool
	var validatorSawTarget, validatorSawBackup bool
	var validatorContent string
	goos := "linux"
	if test.UseZip {
		goos = "windows"
	}
	applier := &updateapply.Applier{
		HTTPClient:    http.DefaultClient,
		GOOS:          goos,
		GOARCH:        "amd64",
		BinaryName:    test.ExtractBinary,
		ExtractBinary: test.ExtractBinary,
		Progress: func(int64, int64) {
			seenStage = seenStage || globHas(filepath.Join(filepath.Dir(target), "updateapply-*"))
			seenTemp = seenTemp || globHas(filepath.Join(os.TempDir(), "updateapply-*"))
		},
	}
	if applier.BinaryName == "" {
		applier.BinaryName = "mytool"
	}
	if test.ValidateError != "" {
		applier.ValidateBinary = func(path string) error {
			validatorSawTarget = path == target
			validatorSawBackup = exists(target + ".bak")
			body, readErr := os.ReadFile(path) //nolint:gosec // path is produced by this oracle's own temp dir walk
			if readErr == nil {
				validatorContent = string(body)
			}
			return errors.New(test.ValidateError)
		}
	}
	applyErr := applier.Apply(context.Background(), &updatecheck.Release{TagName: "v1.0.0", Assets: assets}, target)
	obs := observation{StageDuringDownload: seenStage, TempDuringDownload: seenTemp, ValidatorSawTarget: validatorSawTarget, ValidatorSawBackup: validatorSawBackup, ValidatorTargetContent: validatorContent, Files: []file{}}
	if applyErr != nil {
		text := applyErr.Error()
		switch {
		case strings.Contains(text, "checksum mismatch"):
			obs.ErrorCode = "checksum_mismatch"
		case strings.Contains(text, "no release asset matches"):
			obs.ErrorCode = "missing_asset"
		case strings.Contains(text, "path traversal") || strings.Contains(text, "path escapes"):
			obs.ErrorCode = "path_traversal"
		case strings.Contains(text, "validate installed binary"):
			obs.ErrorCode = "validation_failed"
		default:
			obs.ErrorCode = "apply_failed"
		}
	}
	if data, readErr := os.ReadFile(target); readErr == nil { //nolint:gosec // target path is built by this oracle
		obs.TargetExists, obs.TargetContent = true, string(data)
		if info, statErr := os.Stat(target); statErr == nil {
			obs.TargetMode = uint32(info.Mode().Perm())
			if runtime.GOOS == "windows" {
				obs.TargetMode = 0
			}
		}
	}
	obs.BackupExists = exists(target + ".bak")
	obs.Files = listFiles(root)
	return result{Input: test, Observation: obs}
}

func tarGz(name, content string) []byte {
	var buffer bytes.Buffer
	writer := gzip.NewWriter(&buffer)
	tarWriter := tar.NewWriter(writer)
	if err := tarWriter.WriteHeader(&tar.Header{Name: name, Mode: 0o755, Size: int64(len(content)), Typeflag: tar.TypeReg}); err != nil {
		panic(err)
	}
	if _, err := tarWriter.Write([]byte(content)); err != nil {
		panic(err)
	}
	if err := tarWriter.Close(); err != nil {
		panic(err)
	}
	if err := writer.Close(); err != nil {
		panic(err)
	}
	return buffer.Bytes()
}

func globHas(pattern string) bool { matches, _ := filepath.Glob(pattern); return len(matches) != 0 }
func exists(path string) bool     { _, err := os.Stat(path); return err == nil }

func listFiles(root string) []file {
	files := make([]file, 0)
	_ = filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil || info.IsDir() {
			return nil
		}
		name, _ := filepath.Rel(root, path)
		data, readErr := os.ReadFile(path) //nolint:gosec // path comes from this oracle's own temp dir walk
		if readErr == nil {
			files = append(files, file{Path: filepath.ToSlash(name), Content: string(data), Mode: uint32(info.Mode().Perm())})
		}
		return nil
	})
	sort.Slice(files, func(i, j int) bool { return files[i].Path < files[j].Path })
	if runtime.GOOS == "windows" {
		for i := range files {
			files[i].Mode = 0
		}
	}
	return files
}
