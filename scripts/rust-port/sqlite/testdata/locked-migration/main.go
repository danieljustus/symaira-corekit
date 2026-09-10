// Test-only extension of contentionCase: invoke the production Migrate while
// the same real file-backed writer transaction is held. No child lock holder or
// scheduled release is used by the established oracle.
package main

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing/fstest"
	"time"

	"github.com/danieljustus/symaira-corekit/sqlitekit"
	"modernc.org/sqlite"
)

func must(err error) {
	if err != nil {
		panic(err)
	}
}

func count(db *sql.DB, query string) int {
	var n int
	must(db.QueryRow(query).Scan(&n))
	return n
}

func observe(root string, precreated bool) map[string]any {
	db, err := sqlitekit.Open(filepath.Join(root, fmt.Sprintf("%t.db", precreated)))
	must(err)
	defer db.Close()
	db.SetMaxOpenConns(3)
	db.SetMaxIdleConns(3)
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	var connections []*sql.Conn
	var policies []map[string]any
	for range 3 {
		conn, err := db.Conn(ctx)
		must(err)
		defer conn.Close()
		connections = append(connections, conn)
		var busy, fk int
		var journal string
		must(conn.QueryRowContext(ctx, "PRAGMA busy_timeout").Scan(&busy))
		must(conn.QueryRowContext(ctx, "PRAGMA foreign_keys").Scan(&fk))
		must(conn.QueryRowContext(ctx, "PRAGMA journal_mode").Scan(&journal))
		policies = append(policies, map[string]any{"busy_timeout": busy, "foreign_keys": fk, "journal_mode": journal})
	}
	// Return the contender to the pool used by Migrate; holder and WAL reader
	// stay checked out, forcing three distinct real connections.
	must(connections[2].Close())
	_, err = db.Exec("CREATE TABLE lock_probe (id INTEGER)")
	must(err)
	if precreated {
		must(sqlitekit.Migrate(db, fstest.MapFS{"migrations": &fstest.MapFile{Mode: os.ModeDir | 0700}}))
	}
	migrations := fstest.MapFS{
		"migrations/001_probe.sql": &fstest.MapFile{Data: []byte("CREATE TABLE migration_probe (id INTEGER)")},
	}
	tx, err := connections[0].BeginTx(ctx, nil)
	must(err)
	defer tx.Rollback()
	_, err = tx.ExecContext(ctx, "INSERT INTO lock_probe VALUES (1)")
	must(err)
	start := time.Now()
	migrationErr := sqlitekit.Migrate(db, migrations)
	elapsed := time.Since(start).Seconds()
	if migrationErr == nil {
		panic("locked migration unexpectedly succeeded")
	}
	var cause *sqlite.Error
	if !errors.As(migrationErr, &cause) {
		panic(migrationErr)
	}
	phase := ""
	switch {
	case strings.HasPrefix(migrationErr.Error(), "failed to create schema_migrations table:"):
		phase = "create_table"
	case strings.HasPrefix(migrationErr.Error(), "failed to execute migration 001_probe:"):
		phase = "execute"
	default:
		panic(migrationErr)
	}
	var readerValue int
	must(connections[1].QueryRowContext(ctx, "SELECT COUNT(*) FROM lock_probe").Scan(&readerValue))
	probeAbsent := count(db, "SELECT COUNT(*) FROM sqlite_master WHERE name='migration_probe'") == 0
	trackingExists := count(db, "SELECT COUNT(*) FROM sqlite_master WHERE name='schema_migrations'") == 1
	versionAbsent := !trackingExists || count(db, "SELECT COUNT(*) FROM schema_migrations") == 0
	cleanupStart := time.Now()
	must(tx.Rollback())
	cleanupSeconds := time.Since(cleanupStart).Seconds()
	// A fresh transaction on the same contender proves the failed migration
	// and holder both released their locks; retry also proves no version stuck.
	must(sqlitekit.Migrate(db, migrations))
	_, err = db.Exec("INSERT INTO lock_probe VALUES (2)")
	must(err)
	state := map[string]any{
		"schema_precreated": precreated, "connections": policies,
		"error":        map[string]any{"phase": phase, "sqlite_primary_code": cause.Code() & 255},
		"reader_value": readerValue, "probe_absent": probeAbsent,
		"tracking_exists": trackingExists, "version_absent": versionAbsent,
		"retry_version_count":   count(db, "SELECT COUNT(*) FROM schema_migrations WHERE version='001_probe'"),
		"retry_probe_count":     count(db, "SELECT COUNT(*) FROM sqlite_master WHERE name='migration_probe'"),
		"released_writer_value": count(db, "SELECT id FROM lock_probe"),
	}
	return map[string]any{"state": state, "busy_seconds": elapsed, "rollback_seconds": cleanupSeconds, "diagnostic": migrationErr.Error()}
}

func main() {
	if len(os.Args) != 2 || !filepath.IsAbs(os.Args[1]) {
		panic("usage: locked-migration ABSOLUTE_ISOLATED_DATABASE_ROOT")
	}
	root, err := os.MkdirTemp(os.Args[1], "locked-migration-")
	must(err)
	defer os.RemoveAll(root)
	rows := []map[string]any{observe(root, false), observe(root, true)}
	must(json.NewEncoder(os.Stdout).Encode(map[string]any{
		"cases": rows, "go_version": runtime.Version(), "goos": runtime.GOOS, "goarch": runtime.GOARCH,
	}))
}
