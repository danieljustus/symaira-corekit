package auditkit

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// Sink is an append-only JSONL audit writer with size-based rotation.
// It is safe for concurrent use. Every Append writes one line and flushes
// it to the OS; the chain state (head hash, entry count) is tracked so
// callers can checkpoint with WriteCheckpoint at any time.
type Sink struct {
	mu       sync.Mutex
	path     string
	maxBytes int64
	file     *os.File
	writer   *bufio.Writer
	count    int64
	headHash string
	degraded bool
}

// SinkOption configures a Sink.
type SinkOption func(*Sink)

// WithMaxBytes sets the rotation threshold (default: 10 MiB). When the log
// exceeds it, it is renamed to <path>.1 (overwriting any previous .1) and a
// fresh file starts. Rotation preserves chain verifiability per segment.
func WithMaxBytes(n int64) SinkOption {
	return func(s *Sink) { s.maxBytes = n }
}

const defaultMaxBytes = 10 << 20

// OpenSink opens (creating if needed) the JSONL audit file at path and
// recovers the chain state by replaying existing lines.
func OpenSink(path string, opts ...SinkOption) (*Sink, error) {
	s := &Sink{path: path, maxBytes: defaultMaxBytes}
	for _, opt := range opts {
		opt(s)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return nil, fmt.Errorf("auditkit: mkdir: %w", err)
	}
	f, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		return nil, fmt.Errorf("auditkit: open %s: %w", path, err)
	}
	s.file = f
	s.writer = bufio.NewWriter(f)
	if err := s.recoverState(); err != nil {
		f.Close()
		return nil, err
	}
	return s, nil
}

// recoverState replays the existing file so headHash/count survive restarts.
func (s *Sink) recoverState() error {
	f, err := os.Open(s.path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return fmt.Errorf("auditkit: reopen for replay: %w", err)
	}
	defer f.Close()
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		if line == "" {
			continue
		}
		// A torn write from a crash leaves a partial last line; stop
		// recovery there. The valid prefix stays verifiable.
		var entry chainedEntry
		if err := json.Unmarshal([]byte(line), &entry); err != nil || entry.Hash == "" {
			break
		}
		s.count++
		s.headHash = entry.Hash
	}
	return scanner.Err()
}

// Append writes one JSONL line, updates the chain, and flushes.
// The caller serializes its event payloads; Append does not validate the
// content beyond requiring a single line (newlines are rejected so entries
// stay one-per-line).
func (s *Sink) Append(line string) error {
	if containsLineBreak(line) {
		return fmt.Errorf("auditkit: entry must be a single line")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.degraded {
		return fmt.Errorf("auditkit: sink degraded")
	}
	hash := HashEntry(line, s.headHash)
	entry := chainedEntry{Data: line, Hash: hash}
	data, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("auditkit: marshal: %w", err)
	}
	if _, err := s.writer.Write(append(data, '\n')); err != nil {
		s.degraded = true
		return fmt.Errorf("auditkit: write: %w", err)
	}
	if err := s.writer.Flush(); err != nil {
		s.degraded = true
		return fmt.Errorf("auditkit: flush: %w", err)
	}
	s.count++
	s.headHash = hash
	return s.maybeRotate()
}

// chainedEntry wraps the payload line with its chain link on disk.
type chainedEntry struct {
	Data string `json:"d"`
	Hash string `json:"h"`
}

func containsLineBreak(s string) bool {
	for i := 0; i < len(s); i++ {
		if s[i] == '\n' || s[i] == '\r' {
			return true
		}
	}
	return false
}

// Count returns the number of entries written (including recovered ones).
func (s *Sink) Count() int64 {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.count
}

// HeadHash returns the current chain head hash.
func (s *Sink) HeadHash() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.headHash
}

// Checkpoint writes the anchor file for the current chain state.
func (s *Sink) Checkpoint() error {
	s.mu.Lock()
	hash, count := s.headHash, s.count
	s.mu.Unlock()
	return WriteCheckpoint(DefaultAnchorPath(s.path), hash, count)
}

// Verify reads back the log file and checks chain integrity plus the anchor
// (when present). Returns the verification outcome; an absent anchor yields
// Anchored=false rather than an error.
type Verification struct {
	Entries   int64  // non-empty lines read back
	HeadHash  string // computed chain head over the file contents
	ChainOK   bool   // replayed chain matches the recorded head hash
	Anchored  bool   // an anchor file exists and was checked
	AnchorOK  bool   // count + head match the checkpoint (truncation check)
	Truncated bool   // anchored but count below checkpoint
}

// Verify audits the whole log file against the in-memory chain state and,
// when present, the on-disk anchor.
func (s *Sink) Verify() (Verification, error) {
	s.mu.Lock()
	path, memCount, memHead := s.path, s.count, s.headHash
	s.mu.Unlock()

	v := Verification{Entries: -1}
	lines, err := readLines(path)
	if err != nil {
		return v, err
	}
	var payload []string
	for _, l := range lines {
		var e chainedEntry
		if err := json.Unmarshal([]byte(l), &e); err == nil && e.Hash != "" {
			payload = append(payload, e.Data)
		} else {
			payload = append(payload, l) // legacy un-chained line
		}
	}
	v.Entries = int64(countNonEmpty(payload))
	v.HeadHash = computeHead(payload)
	v.ChainOK = v.HeadHash == memHead && v.Entries == memCount

	anchor, err := ReadCheckpoint(DefaultAnchorPath(path))
	if err != nil {
		return v, err
	}
	if anchor != nil {
		v.Anchored = true
		v.AnchorOK = VerifyAnchor(payload, GenesisHash, anchor)
		v.Truncated = v.Entries < anchor.EntryCount
	}
	return v, nil
}

func computeHead(entries []string) string {
	prev := GenesisHash
	for _, e := range entries {
		if e == "" {
			continue
		}
		prev = HashEntry(e, prev)
	}
	return prev
}

func readLines(path string) ([]string, error) {
	f, err := os.Open(path)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("auditkit: open for verify: %w", err)
	}
	defer f.Close()
	var out []string
	scanner := bufio.NewScanner(f)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)
	for scanner.Scan() {
		if l := scanner.Text(); l != "" {
			out = append(out, l)
		}
	}
	return out, scanner.Err()
}

// Close flushes and closes the underlying file.
func (s *Sink) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.file == nil {
		return nil
	}
	_ = s.writer.Flush()
	err := s.file.Close()
	s.file = nil
	return err
}

// maybeRotate rotates the log when it exceeded maxBytes. Caller holds mu.
func (s *Sink) maybeRotate() error {
	info, err := os.Stat(s.path)
	if err != nil || info.Size() < s.maxBytes {
		return nil // stat errors are non-fatal here
	}
	_ = s.writer.Flush()
	if err := s.file.Close(); err != nil {
		return fmt.Errorf("auditkit: close before rotate: %w", err)
	}
	if err := os.Rename(s.path, s.path+".1"); err != nil {
		return fmt.Errorf("auditkit: rotate: %w", err)
	}
	f, err := os.OpenFile(s.path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o600)
	if err != nil {
		s.degraded = true
		return fmt.Errorf("auditkit: reopen after rotate: %w", err)
	}
	s.file = f
	s.writer = bufio.NewWriter(f)
	return nil
}
