// Package sqlitekit provides SQLite connection management and migration support using pure-Go SQLite.
package sqlitekit

import (
	"database/sql"
	"fmt"
	"io/fs"
	"net/url"
	"path/filepath"
	"sort"
	"strings"

	"github.com/danieljustus/symaira-corekit/fsutil"
)

// Open opens a SQLite database at the given path with WAL mode and recommended pragmas.
// The database is configured for concurrent reads/writes (WAL mode), a 5-second busy
// timeout, and foreign key enforcement. Returns a ready-to-use *sql.DB.
//
// The pragmas are carried in the connection DSN rather than executed once via
// db.Exec. database/sql maintains a connection pool and opens connections lazily;
// a PRAGMA run once only affects the single connection it executed on, and
// busy_timeout and foreign_keys are per-connection settings that otherwise reset
// to SQLite defaults (timeout 0, foreign keys OFF) on every other pooled
// connection. Putting them in the DSN guarantees they apply to every connection.
func Open(path string) (*sql.DB, error) {
	dir := filepath.Dir(path)
	if err := fsutil.SafeMkdirAll(dir, 0700); err != nil {
		return nil, fmt.Errorf("failed to create database directory: %w", err)
	}

	db, err := sql.Open("sqlite", dsn(path))
	if err != nil {
		return nil, fmt.Errorf("failed to open sqlite database: %w", err)
	}

	// Establish a connection eagerly so DSN/pragma errors surface here rather
	// than on the first query.
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("failed to open sqlite database: %w", err)
	}

	return db, nil
}

// dsn builds a modernc.org/sqlite connection string that applies the recommended
// pragmas to every new connection. The path is carried as the opaque part of a
// file: URI so paths containing spaces or other special characters survive.
func dsn(path string) string {
	q := url.Values{}
	q.Add("_pragma", "busy_timeout(5000)")
	q.Add("_pragma", "foreign_keys(1)")
	q.Add("_pragma", "journal_mode(WAL)")
	u := url.URL{Scheme: "file", Opaque: path, RawQuery: q.Encode()}
	return u.String()
}

// Migrate applies pending SQL migrations from the given filesystem.
// The migrationsFS should contain a "migrations" directory with .sql files that
// are sorted lexicographically by filename (e.g., 001_init.sql, 002_add_users.sql).
// Each migration runs inside its own transaction and is tracked in a schema_migrations
// table to ensure idempotency.
func Migrate(db *sql.DB, migrationsFS fs.FS) error {
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS schema_migrations (
		version TEXT PRIMARY KEY,
		applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
	)`); err != nil {
		return fmt.Errorf("failed to create schema_migrations table: %w", err)
	}

	entries, err := fs.ReadDir(migrationsFS, "migrations")
	if err != nil {
		return fmt.Errorf("failed to read migrations directory: %w", err)
	}

	var files []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".sql") {
			files = append(files, e.Name())
		}
	}
	sort.Strings(files)

	for _, name := range files {
		version := strings.TrimSuffix(name, ".sql")

		var count int
		if err := db.QueryRow("SELECT COUNT(*) FROM schema_migrations WHERE version = ?", version).Scan(&count); err != nil {
			return fmt.Errorf("failed to check migration state for %s: %w", version, err)
		}
		if count > 0 {
			continue
		}

		content, err := fs.ReadFile(migrationsFS, "migrations/"+name)
		if err != nil {
			return fmt.Errorf("failed to read migration %s: %w", name, err)
		}

		tx, err := db.Begin()
		if err != nil {
			return fmt.Errorf("failed to begin transaction for migration %s: %w", version, err)
		}

		if _, err := tx.Exec(string(content)); err != nil {
			tx.Rollback()
			return fmt.Errorf("failed to execute migration %s: %w", version, err)
		}

		if _, err := tx.Exec("INSERT INTO schema_migrations (version) VALUES (?)", version); err != nil {
			tx.Rollback()
			return fmt.Errorf("failed to record migration %s: %w", version, err)
		}

		if err := tx.Commit(); err != nil {
			return fmt.Errorf("failed to commit migration %s: %w", version, err)
		}
	}

	return nil
}
