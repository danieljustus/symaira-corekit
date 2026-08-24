package auditkit

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
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
}

// AnchorSchemaVersion is the current version of the ChainAnchor schema.
const AnchorSchemaVersion = 1

// DefaultAnchorPath returns the conventional anchor file path next to the
// log file: <logPath>.anchor.
func DefaultAnchorPath(logPath string) string {
	return logPath + ".anchor"
}

// WriteCheckpoint atomically writes the chain head to the anchor file
// (write-to-temp then rename). The directory is created with 0700 if
// missing; the anchor itself gets 0600.
func WriteCheckpoint(anchorPath, hash string, count int64) error {
	data := fmt.Sprintf(`{"schema_version":%d,"last_entry_hash":%q,"entry_count":%d}`+"\n",
		AnchorSchemaVersion, hash, count)

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

func countNonEmpty(entries []string) int {
	n := 0
	for _, e := range entries {
		if e != "" {
			n++
		}
	}
	return n
}
