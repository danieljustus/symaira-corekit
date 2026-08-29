package auditkit

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

// GenesisHash is the previous-hash value for the first entry in a chain.
const GenesisHash = ""

// HashEntry computes the SHA-256 chain hash of an audit entry line: the
// previous entry's hash is mixed into the digest, so modifying any retained
// entry breaks every subsequent link.
func HashEntry(entryData, prevHash string) string {
	h := sha256.Sum256([]byte(prevHash + entryData))
	return hex.EncodeToString(h[:])
}

// VerifyChain checks that entries form a valid hash chain from initialHash
// (typically GenesisHash) to expectedFinalHash. Empty entries are skipped —
// trailing newlines must not break verification.
func VerifyChain(entries []string, initialHash, expectedFinalHash string) bool {
	prev := initialHash
	for _, entry := range entries {
		if entry == "" {
			continue
		}
		prev = HashEntry(entry, prev)
	}
	return prev == expectedFinalHash
}

// ChainAnchor is the external checkpoint for detecting audit-log truncation.
// Hash-chaining alone detects modification of retained entries but not
// deletion of the tail: an attacker with write access can drop the most
// recent entries and the chain check over the remainder passes. The anchor
// records the head hash and total count so a shortened log no longer
// matches. Store it separately from the log file (different volume or
// stricter permissions).
type ChainAnchor struct {
	// LastEntryHash is the SHA-256 of the most recent audit entry line.
	LastEntryHash string `json:"last_entry_hash"`
	// EntryCount is the total number of non-empty entries in the log.
	EntryCount int64 `json:"entry_count"`
	// SchemaVersion for forward compatibility.
	SchemaVersion int `json:"schema_version"`
	// LogSize is the exact byte size of the checkpointed log file.
	LogSize int64 `json:"log_size,omitempty"`
	// ContentHash authenticates the complete checkpointed log bytes. It keeps
	// the fast recovery path from trusting a same-size modified log.
	ContentHash string `json:"content_hash,omitempty"`
}

// AnchorSchemaVersion is the current version of the ChainAnchor schema.
const AnchorSchemaVersion = 2

// DefaultAnchorPath returns the conventional anchor file path next to the
// log file: <logPath>.anchor.
func DefaultAnchorPath(logPath string) string {
	return logPath + ".anchor"
}

// WriteCheckpoint atomically writes the chain head to the anchor file
// (write-to-temp then rename). The directory is created with 0700 if
// missing; the anchor itself gets 0600.
func WriteCheckpoint(anchorPath, hash string, count int64) error {
	return writeCheckpoint(anchorPath, ChainAnchor{SchemaVersion: AnchorSchemaVersion, LastEntryHash: hash, EntryCount: count})
}

// WriteCheckpointForLog writes an anchor that also authenticates the complete
// log file, allowing recovery to skip JSONL replay while retaining tamper
// detection. The legacy WriteCheckpoint API remains available for callers
// that do not have a log path.
func WriteCheckpointForLog(anchorPath, logPath, hash string, count int64) error {
	info, err := os.Stat(logPath)
	if err != nil {
		return fmt.Errorf("auditkit: stat log: %w", err)
	}
	contentHash, err := hashFile(logPath)
	if err != nil {
		return fmt.Errorf("auditkit: hash log: %w", err)
	}
	return writeCheckpoint(anchorPath, ChainAnchor{
		SchemaVersion: AnchorSchemaVersion,
		LastEntryHash: hash,
		EntryCount:    count,
		LogSize:       info.Size(),
		ContentHash:   contentHash,
	})
}

func writeCheckpoint(anchorPath string, anchor ChainAnchor) error {
	data, err := json.Marshal(anchor)
	if err != nil {
		return fmt.Errorf("auditkit: marshal anchor: %w", err)
	}
	data = append(data, '\n')

	dir := filepath.Dir(anchorPath)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return fmt.Errorf("auditkit: mkdir anchor dir: %w", err)
	}
	tmpPath := anchorPath + ".tmp"
	if err := os.WriteFile(tmpPath, []byte(data), 0o600); err != nil {
		return fmt.Errorf("auditkit: write anchor tmp: %w", err)
	}
	if err := os.Rename(tmpPath, anchorPath); err != nil {
		return fmt.Errorf("auditkit: rename anchor: %w", err)
	}
	return nil
}

func hashFile(path string) (string, error) {
	f, err := os.Open(path) //nolint:gosec // path is constructed by caller
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

// ReadCheckpoint reads the anchor file. A missing anchor returns (nil, nil)
// — there is no checkpoint yet, which callers treat as "unverified".
func ReadCheckpoint(anchorPath string) (*ChainAnchor, error) {
	data, err := os.ReadFile(anchorPath) //nolint:gosec // path is constructed, not user-supplied
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, fmt.Errorf("auditkit: read anchor: %w", err)
	}
	var anchor ChainAnchor
	if err := json.Unmarshal(data, &anchor); err != nil {
		return nil, fmt.Errorf("auditkit: parse anchor: %w", err)
	}
	return &anchor, nil
}

// VerifyAnchor checks both that the entry count matches the checkpoint
// (truncation detection) and that the chain validates (tamper detection).
// A nil anchor fails closed.
func VerifyAnchor(entries []string, initialHash string, anchor *ChainAnchor) bool {
	if anchor == nil {
		return false
	}
	if int64(countNonEmpty(entries)) != anchor.EntryCount {
		return false
	}
	return VerifyChain(entries, initialHash, anchor.LastEntryHash)
}

// VerifyAnchorForLog verifies the chain anchor and the byte-level identity of
// the log. New anchors should use this stronger check; the older helper stays
// compatible with anchors produced without a log path.
func VerifyAnchorForLog(entries []string, initialHash string, anchor *ChainAnchor, logSize int64, contentHash string) bool {
	if anchor == nil || anchor.LogSize != logSize || anchor.ContentHash == "" || anchor.ContentHash != contentHash {
		return false
	}
	return VerifyAnchor(entries, initialHash, anchor)
}

func countNonEmpty(entries []string) int {
	n := 0
	for _, e := range entries {
		if e != "" {
			n++
		}
	}
	return n
}
