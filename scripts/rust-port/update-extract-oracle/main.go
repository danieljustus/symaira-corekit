// Command update-extract-oracle records public archive-extraction behavior.
package main

import (
	"archive/tar"
	"archive/zip"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/danieljustus/symaira-corekit/updatecheck/extract"
)

type entry struct {
	name, body string
	mode       int64
	typeflag   byte
	link       string
}

type archiveCase struct {
	id, kind, expected string
	entries            []entry
	invalid            bool
}

type fileObservation struct {
	Path    string `json:"path"`
	Content string `json:"content"`
	Mode    uint32 `json:"mode"`
}

type errorObservation struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

type observation struct {
	ID             string            `json:"id"`
	Kind           string            `json:"kind"`
	Archive        string            `json:"archive"`
	ArchiveSHA256  string            `json:"archive_sha256"`
	ExpectedBinary string            `json:"expected_binary"`
	SelectedBinary string            `json:"selected_binary,omitempty"`
	Files          []fileObservation `json:"files"`
	Error          *errorObservation `json:"error,omitempty"`
}

func main() {
	dir := filepath.Join("scripts", "rust-port", "update-extract-oracle", "testdata")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		fail(err)
	}
	var cases []observation
	for _, c := range corpus() {
		archive, err := makeArchive(c)
		if err != nil {
			fail(err)
		}
		ext := map[string]string{"tar.gz": ".tar.gz", "zip": ".zip"}[c.kind]
		name := c.id + ext
		if err := os.WriteFile(filepath.Join(dir, name), archive, 0o644); err != nil {
			fail(err)
		}
		cases = append(cases, observe(c, name, archive))
	}
	if err := json.NewEncoder(os.Stdout).Encode(cases); err != nil {
		fail(err)
	}
}

func corpus() []archiveCase {
	const (
		reg     byte = tar.TypeReg
		dir     byte = tar.TypeDir
		symlink byte = tar.TypeSymlink
	)
	return []archiveCase{
		{id: "tar-success", kind: "tar.gz", expected: "tool", entries: []entry{{"bundle/", "", 0o755, dir, ""}, {"bundle/tool", "binary-content", 0o755, reg, ""}, {"bundle/LICENSE", "MIT", 0o644, reg, ""}}},
		{id: "tar-large-mode", kind: "tar.gz", expected: "tool", entries: []entry{{"bundle/tool", strings.Repeat("A", 10000), 0o751, reg, ""}}},
		{id: "tar-symlink-escape-skipped", kind: "tar.gz", expected: "tool", entries: []entry{{"link", "", 0, symlink, "../../outside"}, {"link/escaped", "safe", 0o600, reg, ""}, {"bundle/tool", "safe-binary", 0o755, reg, ""}}},
		{id: "tar-traversal", kind: "tar.gz", expected: "tool", entries: []entry{{"../escape", "bad", 0o644, reg, ""}}},
		{id: "tar-absolute", kind: "tar.gz", expected: "tool", entries: []entry{{"/outside", "bad", 0o644, reg, ""}}},
		{id: "tar-invalid-gzip", kind: "tar.gz", expected: "tool", invalid: true},
		{id: "tar-empty", kind: "tar.gz", expected: "tool"},
		{id: "zip-success", kind: "zip", expected: "tool.exe", entries: []entry{{"bundle/tool.exe", "binary-content-win", 0o751, reg, ""}, {"bundle/LICENSE", "MIT", 0o640, reg, ""}}},
		{id: "zip-large", kind: "zip", expected: "tool.exe", entries: []entry{{"bundle/tool.exe", strings.Repeat("B", 10000), 0o755, reg, ""}}},
		{id: "zip-traversal", kind: "zip", expected: "tool.exe", entries: []entry{{"../escape", "bad", 0o644, reg, ""}}},
		{id: "zip-invalid", kind: "zip", expected: "tool.exe", invalid: true},
		{id: "zip-empty", kind: "zip", expected: "tool.exe"},
	}
}

func makeArchive(c archiveCase) ([]byte, error) {
	if c.invalid {
		if c.kind == "tar.gz" {
			return []byte("not-gzip-data"), nil
		}
		return []byte("not-zip-data"), nil
	}
	var buf bytes.Buffer
	if c.kind == "tar.gz" {
		gz := gzip.NewWriter(&buf)
		tarWriter := tar.NewWriter(gz)
		for _, e := range c.entries {
			h := &tar.Header{Name: e.name, Typeflag: e.typeflag, Mode: e.mode, Linkname: e.link, Size: int64(len(e.body))}
			if err := tarWriter.WriteHeader(h); err != nil {
				return nil, err
			}
			if e.typeflag == tar.TypeReg {
				if _, err := io.WriteString(tarWriter, e.body); err != nil {
					return nil, err
				}
			}
		}
		if err := tarWriter.Close(); err != nil {
			return nil, err
		}
		if err := gz.Close(); err != nil {
			return nil, err
		}
		return buf.Bytes(), nil
	}
	zw := zip.NewWriter(&buf)
	for _, e := range c.entries {
		h := &zip.FileHeader{Name: e.name, Method: zip.Deflate}
		h.SetMode(os.FileMode(e.mode))
		w, err := zw.CreateHeader(h)
		if err != nil {
			return nil, err
		}
		if _, err := io.WriteString(w, e.body); err != nil {
			return nil, err
		}
	}
	if err := zw.Close(); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

func observe(c archiveCase, name string, archive []byte) observation {
	dest, err := os.MkdirTemp("", "update-extract-oracle-")
	if err != nil {
		fail(err)
	}
	defer os.RemoveAll(dest)
	var selected string
	if c.kind == "tar.gz" {
		selected, err = extract.ExtractTarGz(archive, dest, c.expected)
	} else {
		selected, err = extract.ExtractZip(archive, dest, c.expected)
	}
	o := observation{ID: c.id, Kind: c.kind, Archive: filepath.ToSlash(filepath.Join("scripts/rust-port/update-extract-oracle/testdata", name)), ArchiveSHA256: digest(archive), ExpectedBinary: c.expected, Files: []fileObservation{}}
	if err != nil {
		code := "io"
		switch {
		case errors.Is(err, extract.ErrPathTraversal):
			code = "path_traversal"
		case errors.Is(err, extract.ErrBinaryNotFound):
			code = "binary_not_found"
		case strings.HasPrefix(err.Error(), "decompress gzip:"):
			code = "invalid_gzip"
		case strings.HasPrefix(err.Error(), "open zip archive:"):
			code = "invalid_zip"
		}
		o.Error = &errorObservation{Code: code, Message: err.Error()}
	} else {
		o.SelectedBinary, _ = filepath.Rel(dest, selected)
		o.SelectedBinary = filepath.ToSlash(o.SelectedBinary)
	}
	_ = filepath.WalkDir(dest, func(path string, d os.DirEntry, walkErr error) error {
		if walkErr != nil || d.IsDir() {
			return walkErr
		}
		info, statErr := d.Info()
		if statErr != nil {
			return statErr
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		rel, _ := filepath.Rel(dest, path)
		o.Files = append(o.Files, fileObservation{Path: filepath.ToSlash(rel), Content: string(data), Mode: uint32(info.Mode().Perm())})
		return nil
	})
	sort.Slice(o.Files, func(i, j int) bool { return o.Files[i].Path < o.Files[j].Path })
	return o
}

func digest(b []byte) string { sum := sha256.Sum256(b); return hex.EncodeToString(sum[:]) }

func fail(err error) { fmt.Fprintln(os.Stderr, err); os.Exit(1) }
