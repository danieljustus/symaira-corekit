package sqlitekit

import (
	"database/sql"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"testing/fstest"

	_ "modernc.org/sqlite"
)

func TestOpen_MkdirFailure(t *testing.T) {
	if os.Geteuid() == 0 {
		t.Skip("running as root; permission checks are meaningless")
	}
	parent := t.TempDir()
	if err := os.Chmod(parent, 0500); err != nil {
		t.Fatal(err)
	}
	defer os.Chmod(parent, 0700)

	db, err := Open(filepath.Join(parent, "sub", "test.db"))
	if err == nil {
		db.Close()
		t.Fatal("Open under a read-only parent = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to create database directory") {
		t.Fatalf("error = %v, want directory-creation wrap", err)
	}
}

func TestOpen_PingFailure(t *testing.T) {
	// A path that is an existing directory cannot be opened as a SQLite
	// database; SafeMkdirAll succeeds (it exists), sql.Open succeeds, and
	// the eager Ping surfaces the DSN error.
	dir := t.TempDir()
	db, err := Open(dir)
	if err == nil {
		db.Close()
		t.Fatal("Open on a directory = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to open sqlite database") {
		t.Fatalf("error = %v, want ping-failure wrap", err)
	}
}

func TestMigrate_CreateTableFailure(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	db.Close()

	err = Migrate(db, testMigrations(t))
	if err == nil {
		t.Fatal("Migrate on a closed db = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to create schema_migrations table") {
		t.Fatalf("error = %v, want create-table wrap", err)
	}
}

func TestMigrate_ReadDirFailure(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	err = Migrate(db, fstest.MapFS{})
	if err == nil {
		t.Fatal("Migrate with an empty filesystem = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to read migrations directory") {
		t.Fatalf("error = %v, want read-dir wrap", err)
	}
}

func TestMigrate_VersionQueryFailure(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	// A view named schema_migrations makes the CREATE TABLE IF NOT EXISTS a
	// no-op, but its query (a view over a missing table) fails on the
	// version-count SELECT.
	if _, err := db.Exec("CREATE VIEW schema_migrations AS SELECT 1 AS version, datetime('now') AS applied_at FROM missing_table"); err != nil {
		t.Fatalf("create view: %v", err)
	}

	err = Migrate(db, testMigrations(t))
	if err == nil {
		t.Fatal("Migrate with a broken schema_migrations view = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to check migration state") {
		t.Fatalf("error = %v, want version-query wrap", err)
	}
}

// readFileErrorFS fails every ReadFile while delegating everything else.
type readFileErrorFS struct {
	fs.FS
}

func (f readFileErrorFS) ReadFile(string) ([]byte, error) {
	return nil, os.ErrNotExist
}

func TestMigrate_ReadFileFailure(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	err = Migrate(db, readFileErrorFS{testMigrations(t)})
	if err == nil {
		t.Fatal("Migrate with unreadable migration files = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to read migration") {
		t.Fatalf("error = %v, want read-file wrap", err)
	}
}

func TestMigrate_ExecFailureRollsBack(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	migrations := fstest.MapFS{
		"migrations/001_partial.sql": &fstest.MapFile{
			Data: []byte("CREATE TABLE rollback_probe (id INTEGER);\nTHIS IS NOT VALID SQL;"),
		},
	}

	err = Migrate(db, migrations)
	if err == nil {
		t.Fatal("Migrate with malformed SQL = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to execute migration") {
		t.Fatalf("error = %v, want exec wrap", err)
	}

	// The transaction must have rolled back: the table from the partial
	// migration must not exist and the version must not be recorded.
	var name string
	queryErr := db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='rollback_probe'").Scan(&name)
	if !errors.Is(queryErr, sql.ErrNoRows) {
		t.Fatalf("rollback_probe still present after failed migration (query err = %v)", queryErr)
	}
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations WHERE version = '001_partial'").Scan(&count); err != nil {
		t.Fatalf("query schema_migrations: %v", err)
	}
	if count != 0 {
		t.Fatalf("failed migration recorded as applied: count = %d", count)
	}
}

func TestMigrate_InsertFailureRollsBack(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	// A read-only view over a real table makes the version-count query work
	// (count 0) but the INSERT INTO schema_migrations fail, which forces the
	// rollback of the already-executed migration.
	if _, err := db.Exec("CREATE TABLE versions_underlying (version TEXT, applied_at TEXT)"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Exec("CREATE VIEW schema_migrations AS SELECT version, applied_at FROM versions_underlying"); err != nil {
		t.Fatal(err)
	}

	err = Migrate(db, testMigrations(t))
	if err == nil {
		t.Fatal("Migrate with a read-only schema_migrations view = nil, want error")
	}
	if !strings.Contains(err.Error(), "failed to record migration") {
		t.Fatalf("error = %v, want record wrap", err)
	}

	// The executed migration must have been rolled back.
	var name string
	queryErr := db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='test_items'").Scan(&name)
	if !errors.Is(queryErr, sql.ErrNoRows) {
		t.Fatalf("test_items still present after failed insert (query err = %v)", queryErr)
	}
}

func TestMigrate_FailureLeavesIdempotentState(t *testing.T) {
	tmpDir := t.TempDir()
	db, err := Open(filepath.Join(tmpDir, "test.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()

	bad := fstest.MapFS{
		"migrations/001_ok.sql":  &fstest.MapFile{Data: []byte("CREATE TABLE ok_probe (id INTEGER);")},
		"migrations/002_bad.sql": &fstest.MapFile{Data: []byte("NOT SQL AT ALL")},
	}

	if err := Migrate(db, bad); err == nil {
		t.Fatal("Migrate with a bad second migration = nil, want error")
	}

	// The first migration applied and is recorded; the second did not.
	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations WHERE version = '001_ok'").Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("001_ok recorded = %d, want 1", count)
	}
	var name string
	if err := db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='ok_probe'").Scan(&name); err != nil {
		t.Fatalf("ok_probe missing after partial success: %v", err)
	}

	// Re-running stays deterministic: same failure, no state change.
	if err := Migrate(db, bad); err == nil {
		t.Fatal("second Migrate with a bad migration = nil, want error")
	}
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations WHERE version = '001_ok'").Scan(&count); err != nil {
		t.Fatal(err)
	}
	if count != 1 {
		t.Fatalf("001_ok recorded after rerun = %d, want still 1", count)
	}
}
