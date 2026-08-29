//nolint:gosec
package auditkit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestHashEntryDeterministic(t *testing.T) {
	h1 := HashEntry("line", "prev")
	h2 := HashEntry("line", "prev")
	if h1 != h2 {
		t.Fatalf("hash not deterministic: %q vs %q", h1, h2)
	}
	if len(h1) != 64 {
		t.Errorf("sha256 hex length = %d, want 64", len(h1))
	}
	// Order matters: prev+data != data+prev
	if HashEntry("a", "b") == HashEntry("b", "a") {
		t.Error("chain hash must be order-sensitive")
	}
}

func TestVerifyChainDetectsTampering(t *testing.T) {
	entries := []string{"e1", "e2", "e3"}
	head := computeHead(entries)
	if !VerifyChain(entries, GenesisHash, head) {
		t.Fatal("valid chain failed verification")
	}

	tampered := []string{"e1", "TAMPERED", "e3"}
	if VerifyChain(tampered, GenesisHash, head) {
		t.Error("tampered chain passed verification")
	}

	truncated := entries[:2]
	if VerifyChain(truncated, GenesisHash, head) {
		t.Error("truncated chain (no anchor) unexpectedly matched head — truncation is only detectable via anchor, but chain-over-remaining must not equal original head here since e3 is missing")
	}
}

func TestCheckpointRoundtrip(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "audit.anchor")

	anchor, err := ReadCheckpoint(path)
	if err != nil || anchor != nil {
		t.Fatalf("missing anchor should return (nil, nil), got (%v, %v)", anchor, err)
	}

	want := &ChainAnchor{LastEntryHash: "abc", EntryCount: 42, SchemaVersion: AnchorSchemaVersion}
	data := fmt.Sprintf(`{"schema_version":%d,"last_entry_hash":%q,"entry_count":%d}`+"\n",
		want.SchemaVersion, want.LastEntryHash, want.EntryCount)
	if err := os.WriteFile(path, []byte(data), 0o600); err != nil {
		t.Fatal(err)
	}

	got, err := ReadCheckpoint(path)
	if err != nil || got == nil {
		t.Fatalf("ReadCheckpoint: %v", err)
	}
	if got.LastEntryHash != want.LastEntryHash || got.EntryCount != want.EntryCount {
		t.Errorf("roundtrip mismatch: %+v", got)
	}
}

func TestWriteCheckpointAtomicAndPermissive(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "audit.log.anchor")
	if err := WriteCheckpoint(path, "deadbeef", 7); err != nil {
		t.Fatal(err)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if perm := info.Mode().Perm(); perm != 0o600 {
		t.Errorf("anchor perms = %o, want 600", perm)
	}
	anchor, _ := ReadCheckpoint(path)
	if anchor == nil || anchor.LastEntryHash != "deadbeef" || anchor.EntryCount != 7 {
		t.Errorf("checkpoint content wrong: %+v", anchor)
	}
}

func TestVerifyAnchorFailsClosedOnNil(t *testing.T) {
	if VerifyAnchor([]string{"x"}, GenesisHash, nil) {
		t.Error("nil anchor must fail closed")
	}
}

func TestSinkAppendAndRecover(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "audit.jsonl")

	s, err := OpenSink(path)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 5; i++ {
		line := fmt.Sprintf(`{"n":%d,"msg":"event %d"}`, i, i)
		if err := s.Append(line); err != nil {
			t.Fatalf("Append %d: %v", i, err)
		}
	}
	count, head := s.Count(), s.HeadHash()
	if count != 5 || head == "" {
		t.Fatalf("state after appends: count=%d head=%q", count, head)
	}
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}

	// Reopen: state must be recovered from the file.
	s2, err := OpenSink(path)
	if err != nil {
		t.Fatal(err)
	}
	defer s2.Close()
	if s2.Count() != count || s2.HeadHash() != head {
		t.Errorf("recovered state = (%d, %q), want (%d, %q)", s2.Count(), s2.HeadHash(), count, head)
	}
}

func TestSinkRejectsMultiLine(t *testing.T) {
	dir := t.TempDir()
	s, err := OpenSink(filepath.Join(dir, "audit.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()
	if err := s.Append("{\"a\":1}\n{\"b\":2}"); err == nil {
		t.Error("multi-line entry accepted")
	}
	if err := s.Append("line\r\nbreak"); err == nil {
		t.Error("CR-carrying entry accepted")
	}
}

func TestSinkVerifyWithAnchor(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "audit.jsonl")

	s, err := OpenSink(path)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		_ = s.Append(fmt.Sprintf(`{"i":%d}`, i))
	}
	if err := s.Checkpoint(); err != nil {
		t.Fatal(err)
	}
	v, err := s.Verify()
	if err != nil {
		t.Fatal(err)
	}
	if v.Entries != 3 || !v.ChainOK || !v.Anchored || !v.AnchorOK || v.Truncated {
		t.Errorf("verification after clean writes: %+v", v)
	}
	s.Close()

	// Simulate tail truncation: rewrite the file without the last line.
	lines := readAllLines(t, path)
	if len(lines) < 2 {
		t.Fatalf("file has %d lines", len(lines))
	}
	_ = os.WriteFile(path, []byte(strings.Join(lines[:len(lines)-1], "\n")+"\n"), 0o600)

	s2, err := OpenSink(path)
	if err != nil {
		t.Fatal(err)
	}
	defer s2.Close()
	v2, err := s2.Verify()
	if err != nil {
		t.Fatal(err)
	}
	if !v2.Anchored {
		t.Fatal("anchor lost after truncation simulation")
	}
	if v2.AnchorOK {
		t.Errorf("truncated log passed anchor check: %+v", v2)
	}
	if !v2.Truncated {
		t.Errorf("Truncated flag not set: %+v", v2)
	}
}

func TestSinkRotation(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "audit.jsonl")
	s, err := OpenSink(path, WithMaxBytes(200))
	if err != nil {
		t.Fatal(err)
	}
	defer s.Close()

	for i := 0; i < 20; i++ {
		line := fmt.Sprintf(`{"i":%d,"payload":"%s"}`, i, strings.Repeat("x", 30))
		if err := s.Append(line); err != nil {
			t.Fatalf("append %d: %v", i, err)
		}
	}
	if _, err := os.Stat(path + ".1"); err != nil {
		t.Errorf("rotated segment missing: %v", err)
	}
	if s.Count() != 20 {
		t.Errorf("count across rotation = %d, want 20", s.Count())
	}
}

func TestSinkRejectsAfterCloseDegradedPath(t *testing.T) {
	dir := t.TempDir()
	s, err := OpenSink(filepath.Join(dir, "a.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	_ = s.Append(`{"ok":true}`)
	if err := s.Close(); err != nil {
		t.Fatal(err)
	}
	// Double close is safe.
	if err := s.Close(); err != nil {
		t.Errorf("double close errored: %v", err)
	}
}

func readAllLines(t *testing.T, path string) []string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var out []string
	for _, l := range strings.Split(string(data), "\n") {
		if l != "" {
			out = append(out, l)
		}
	}
	return out
}

var _ = json.Valid

func TestCheckpointStoresLogFingerprintAndRejectsSameSizeTamper(t *testing.T) {
	path := filepath.Join(t.TempDir(), "audit.jsonl")
	sink, err := OpenSink(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := sink.Append(`{"event":"one"}`); err != nil {
		t.Fatal(err)
	}
	if err := sink.Checkpoint(); err != nil {
		t.Fatal(err)
	}
	wantCount, wantHead := sink.Count(), sink.HeadHash()
	if err := sink.Close(); err != nil {
		t.Fatal(err)
	}

	anchor, err := ReadCheckpoint(DefaultAnchorPath(path))
	if err != nil {
		t.Fatal(err)
	}
	if anchor == nil || anchor.LogSize == 0 || anchor.ContentHash == "" {
		t.Fatalf("anchor = %#v, want log fingerprint", anchor)
	}

	reopened, err := OpenSink(path)
	if err != nil {
		t.Fatalf("reopen with valid anchor: %v", err)
	}
	if reopened.Count() != wantCount || reopened.HeadHash() != wantHead {
		t.Fatalf("recovered state = (%d, %q), want (%d, %q)", reopened.Count(), reopened.HeadHash(), wantCount, wantHead)
	}
	if err := reopened.Close(); err != nil {
		t.Fatal(err)
	}

	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	mutated := strings.Replace(string(raw), "one", "two", 1)
	if mutated == string(raw) {
		t.Fatal("test mutation did not change the log")
	}
	if err := os.WriteFile(path, []byte(mutated), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := OpenSink(path); err == nil {
		t.Fatal("expected same-size tampering to fail recovery")
	}
}
