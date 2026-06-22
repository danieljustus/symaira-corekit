package sqlitekit

import (
	"context"
	"database/sql"
	"embed"
	"io/fs"
	"os"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

//go:embed testdata/migrations/*.sql
var testMigrationsRaw embed.FS

func testMigrations(t *testing.T) fs.FS {
	t.Helper()
	sub, err := fs.Sub(testMigrationsRaw, "testdata")
	if err != nil {
		t.Fatalf("fs.Sub() error = %v", err)
	}
	return sub
}

func TestOpen(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer db.Close()

	if err := db.Ping(); err != nil {
		t.Fatalf("db.Ping() error = %v", err)
	}

	var journalMode string
	if err := db.QueryRow("PRAGMA journal_mode").Scan(&journalMode); err != nil {
		t.Fatalf("failed to query journal_mode: %v", err)
	}
	if journalMode != "wal" {
		t.Errorf("journal_mode = %q, want %q", journalMode, "wal")
	}

	var fkEnabled int
	if err := db.QueryRow("PRAGMA foreign_keys").Scan(&fkEnabled); err != nil {
		t.Fatalf("failed to query foreign_keys: %v", err)
	}
	if fkEnabled != 1 {
		t.Errorf("foreign_keys = %d, want 1", fkEnabled)
	}

	if _, err := os.Stat(dbPath); os.IsNotExist(err) {
		t.Error("database file was not created")
	}
}

// TestOpen_PragmasOnEveryConnection guards against the per-connection pragma
// pitfall: PRAGMA statements run once on a *sql.DB only affect the single pooled
// connection they execute on, while foreign_keys and busy_timeout are
// per-connection settings that otherwise reset to SQLite defaults on every other
// connection the pool opens. Holding several connections open at once forces the
// pool to create distinct connections, each of which must carry the pragmas.
// The path deliberately contains a space to exercise DSN path handling.
func TestOpen_PragmasOnEveryConnection(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "with space", "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer db.Close()

	ctx := context.Background()
	const n = 5
	conns := make([]*sql.Conn, 0, n)
	for i := 0; i < n; i++ {
		c, err := db.Conn(ctx)
		if err != nil {
			t.Fatalf("db.Conn() #%d error = %v", i, err)
		}
		conns = append(conns, c)
	}
	defer func() {
		for _, c := range conns {
			_ = c.Close()
		}
	}()

	for i, c := range conns {
		var fkEnabled int
		if err := c.QueryRowContext(ctx, "PRAGMA foreign_keys").Scan(&fkEnabled); err != nil {
			t.Fatalf("conn #%d query foreign_keys: %v", i, err)
		}
		if fkEnabled != 1 {
			t.Errorf("conn #%d foreign_keys = %d, want 1", i, fkEnabled)
		}

		var busyTimeout int
		if err := c.QueryRowContext(ctx, "PRAGMA busy_timeout").Scan(&busyTimeout); err != nil {
			t.Fatalf("conn #%d query busy_timeout: %v", i, err)
		}
		if busyTimeout != 5000 {
			t.Errorf("conn #%d busy_timeout = %d, want 5000", i, busyTimeout)
		}
	}
}

func TestOpen_CreatesParentDir(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "subdir", "nested", "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer db.Close()

	if _, err := os.Stat(dbPath); os.IsNotExist(err) {
		t.Error("database file was not created in nested directory")
	}
}

func TestMigrate(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer db.Close()

	if err := Migrate(db, testMigrations(t)); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	var tableName string
	err = db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='test_items'").Scan(&tableName)
	if err != nil {
		t.Fatalf("test_items table not created: %v", err)
	}

	var indexName string
	err = db.QueryRow("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_test_items_name'").Scan(&indexName)
	if err != nil {
		t.Fatalf("idx_test_items_name index not created: %v", err)
	}

	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations").Scan(&count); err != nil {
		t.Fatalf("failed to query schema_migrations: %v", err)
	}
	if count != 2 {
		t.Errorf("schema_migrations count = %d, want 2", count)
	}
}

func TestMigrate_Idempotent(t *testing.T) {
	tmpDir := t.TempDir()
	dbPath := filepath.Join(tmpDir, "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open() error = %v", err)
	}
	defer db.Close()

	if err := Migrate(db, testMigrations(t)); err != nil {
		t.Fatalf("first Migrate() error = %v", err)
	}

	if err := Migrate(db, testMigrations(t)); err != nil {
		t.Fatalf("second Migrate() error = %v", err)
	}

	var count int
	if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations").Scan(&count); err != nil {
		t.Fatalf("failed to query schema_migrations: %v", err)
	}
	if count != 2 {
		t.Errorf("schema_migrations count = %d, want 2 (idempotent)", count)
	}
}

func TestMigrate_InMemory(t *testing.T) {
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		t.Fatalf("sql.Open() error = %v", err)
	}
	defer db.Close()

	if err := Migrate(db, testMigrations(t)); err != nil {
		t.Fatalf("Migrate() error = %v", err)
	}

	var tableName string
	err = db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='test_items'").Scan(&tableName)
	if err != nil {
		t.Fatalf("test_items table not created: %v", err)
	}
}
