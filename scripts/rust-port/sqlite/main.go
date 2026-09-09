package main

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"syscall"
	"testing/fstest"
	"time"

	"github.com/danieljustus/symaira-corekit/sqlitekit"
	_ "modernc.org/sqlite"
)

//go:embed migrations/*.sql
var migrations embed.FS

type observation struct {
	ID       string         `json:"id"`
	Success  bool           `json:"success"`
	State    map[string]any `json:"state,omitempty"`
	Negative []negative     `json:"negative,omitempty"`
}
type negative struct {
	Name          string         `json:"name"`
	Error         string         `json:"error"`
	ErrorContains string         `json:"error_contains"`
	RolledBack    bool           `json:"rolled_back"`
	Cause         map[string]any `json:"cause"`
}
type report struct {
	Oracle struct {
		Implementation string `json:"implementation"`
		GoVersion      string `json:"go_version"`
	} `json:"oracle"`
	Cases []observation `json:"cases"`
}

func main() {
	if len(os.Args) != 1 {
		fatal("usage: sqlite-oracle takes no arguments")
	}
	r, err := run()
	if err != nil {
		fatal(err.Error())
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetEscapeHTML(false)
	if err := enc.Encode(r); err != nil {
		fatal(err.Error())
	}
}

func run() (report, error) {
	var r report
	r.Oracle.Implementation = "sqlitekit.Open/Migrate"
	r.Oracle.GoVersion = runtime.Version()
	for _, fn := range []func() (observation, error){openCase, pragmaCase, migrationCase, idempotentCase, rollbackCase, errorCase} {
		c, err := fn()
		if err != nil {
			return report{}, err
		}
		r.Cases = append(r.Cases, c)
	}
	return r, nil
}

func openCase() (observation, error) {
	d := mustTemp()
	defer os.RemoveAll(d)
	path := filepath.Join(d, "nested", "database.db")
	db, err := sqlitekit.Open(path)
	if err != nil {
		return observation{ID: "SQL-001"}, err
	}
	defer db.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	var one int
	if err := db.QueryRowContext(ctx, "SELECT 1").Scan(&one); err != nil {
		return observation{}, err
	}
	st, err := os.Stat(path)
	if err != nil {
		return observation{}, err
	}
	parent, err := os.Stat(filepath.Dir(path))
	if err != nil {
		return observation{}, err
	}
	_, dirErr := sqlitekit.Open(d)
	parentFile := filepath.Join(d, "not-a-directory")
	if err := os.WriteFile(parentFile, []byte("file"), 0600); err != nil {
		return observation{}, err
	}
	_, parentErr := sqlitekit.Open(filepath.Join(parentFile, "db.sqlite"))
	state := map[string]any{
		"ping": one == 1, "database_exists": true, "parent_exists": true,
		"database_mode": fmt.Sprintf("%04o", st.Mode().Perm()), "parent_mode": fmt.Sprintf("%04o", parent.Mode().Perm()),
		"native_goos": runtime.GOOS, "native_goarch": runtime.GOARCH,
		"open_errors": map[string]string{"missing_directory": normalizeError(dirErr, d), "parent_file": normalizeError(parentErr, d)},
		"open_causes": map[string]any{"missing_directory": errorCause(dirErr), "parent_file": errorCause(parentErr)},
	}
	return observation{ID: "SQL-001", Success: one == 1 && dirErr != nil && parentErr != nil, State: state}, nil
}

func pragmaCase() (observation, error) {
	d := mustTemp()
	defer os.RemoveAll(d)
	db, err := sqlitekit.Open(filepath.Join(d, "database.db"))
	if err != nil {
		return observation{}, err
	}
	defer db.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	var conns []*sql.Conn
	defer func() {
		for _, c := range conns {
			_ = c.Close()
		}
	}()
	for i := 0; i < 5; i++ {
		c, err := db.Conn(ctx)
		if err != nil {
			return observation{}, err
		}
		conns = append(conns, c)
	}
	values := make([]map[string]any, 0, len(conns))
	for _, c := range conns {
		var fk, busy int
		var journal string
		if err := c.QueryRowContext(ctx, "PRAGMA foreign_keys").Scan(&fk); err != nil {
			return observation{}, err
		}
		if err := c.QueryRowContext(ctx, "PRAGMA busy_timeout").Scan(&busy); err != nil {
			return observation{}, err
		}
		if err := c.QueryRowContext(ctx, "PRAGMA journal_mode").Scan(&journal); err != nil {
			return observation{}, err
		}
		values = append(values, map[string]any{"foreign_keys": fk, "busy_timeout": busy, "journal_mode": strings.ToLower(journal)})
	}
	contention := contentionCase(db)
	return observation{ID: "SQL-002", Success: len(values) == 5 && contention["observed"] == true && contention["blocked"] == true && contention["reader_succeeded"] == true, State: map[string]any{"connections": values, "contention": contention}}, nil
}

func contentionCase(db *sql.DB) map[string]any {
	ctx, cancel := context.WithTimeout(context.Background(), 8*time.Second)
	defer cancel()
	if _, err := db.ExecContext(ctx, "CREATE TABLE IF NOT EXISTS lock_probe (id INTEGER)"); err != nil {
		return map[string]any{"observed": false, "error": err.Error()}
	}
	conn, err := db.Conn(ctx)
	if err != nil {
		return map[string]any{"observed": false, "error": err.Error()}
	}
	defer conn.Close()
	tx, err := conn.BeginTx(ctx, nil)
	if err != nil {
		return map[string]any{"observed": false, "error": err.Error()}
	}
	_, execErr := tx.ExecContext(ctx, "INSERT INTO lock_probe VALUES (1)")
	start := time.Now()
	_, writerErr := db.ExecContext(ctx, "INSERT INTO lock_probe VALUES (2)")
	elapsed := time.Since(start)
	var readerValue int
	readerErr := db.QueryRowContext(ctx, "SELECT COUNT(*) FROM lock_probe").Scan(&readerValue)
	txRollbackErr := tx.Rollback()
	return map[string]any{
		"observed": true, "tx_exec_succeeded": execErr == nil, "blocked": writerErr != nil,
		"writer_error": errorString(writerErr), "reader_succeeded": readerErr == nil && readerValue == 0,
		"writer_cause": errorCause(writerErr),
		"reader_value": readerValue, "rollback_succeeded": txRollbackErr == nil,
		"within_busy_timeout": elapsed >= 4*time.Second && elapsed <= 6*time.Second,
	}
}

func migrationCase() (observation, error)  { return migrateObserved("SQL-003", false) }
func idempotentCase() (observation, error) { return migrateObserved("SQL-004", true) }

func migrateObserved(id string, repeated bool) (observation, error) {
	d := mustTemp()
	defer os.RemoveAll(d)
	db, err := sqlitekit.Open(filepath.Join(d, "database.db"))
	if err != nil {
		return observation{}, err
	}
	defer db.Close()
	if err := sqlitekit.Migrate(db, migrations); err != nil {
		return observation{}, err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if _, err := db.ExecContext(ctx, "INSERT INTO test_items (id, name) VALUES ('item-1', 'alpha')"); err != nil {
		return observation{}, err
	}
	before, err := migrationState(ctx, db)
	if err != nil {
		return observation{}, err
	}
	state := map[string]any{"migration_count": before.count, "versions": before.versions, "schema": before.schema, "data": before.data, "applied_at": before.appliedAt, "applied_at_utc": before.appliedAtUTC, "repeat": repeated, "large_integer": before.largeInteger, "null_value": before.nullValue}
	if repeated {
		invalid := countingFS{FS: fstestFS(map[string]string{"migrations/001_test.sql": "THIS IS INVALID SQL;", "migrations/002_index.sql": "THIS IS ALSO INVALID SQL;"})}
		if err := sqlitekit.Migrate(db, &invalid); err != nil {
			return observation{}, err
		}
		after, err := migrationState(ctx, db)
		if err != nil {
			return observation{}, err
		}
		state["replacement_error_nil"] = true
		state["replacement_read_attempts"] = invalid.reads
		state["rows_unchanged"] = reflect.DeepEqual(before.data, after.data)
		state["versions_unchanged"] = reflect.DeepEqual(before.versions, after.versions)
		state["schema_unchanged"] = reflect.DeepEqual(before.schema, after.schema)
		state["applied_at_unchanged"] = reflect.DeepEqual(before.appliedAt, after.appliedAt)
		return observation{ID: id, Success: invalid.reads == 0 && reflect.DeepEqual(before, after), State: state}, nil
	}
	return observation{ID: id, Success: before.count == 2 && before.appliedAtUTC, State: state}, nil
}

type migrationSnapshot struct {
	count        int
	versions     []string
	schema       []map[string]string
	data         []map[string]any
	appliedAt    []string
	appliedAtUTC bool
	largeInteger int64
	nullValue    any
}

func migrationState(ctx context.Context, db *sql.DB) (migrationSnapshot, error) {
	var s migrationSnapshot
	if err := db.QueryRowContext(ctx, "SELECT COUNT(*) FROM schema_migrations").Scan(&s.count); err != nil {
		return s, err
	}
	rows, err := db.QueryContext(ctx, "SELECT version, applied_at FROM schema_migrations ORDER BY version")
	if err != nil {
		return s, err
	}
	defer rows.Close()
	for rows.Next() {
		var version, applied string
		if err := rows.Scan(&version, &applied); err != nil {
			return s, err
		}
		s.versions = append(s.versions, version)
		s.appliedAt = append(s.appliedAt, applied)
		t, err := time.Parse(time.RFC3339, applied)
		if err != nil {
			t, err = time.ParseInLocation("2006-01-02 15:04:05", applied, time.UTC)
		}
		if err != nil || t.IsZero() || t.Location() != time.UTC {
			return s, fmt.Errorf("invalid applied_at %q", applied)
		}
	}
	if err := rows.Err(); err != nil {
		return s, err
	}
	s.appliedAtUTC = len(s.appliedAt) == s.count && s.count > 0
	schemaRows, err := db.QueryContext(ctx, "SELECT type,name,sql FROM sqlite_master WHERE name IN ('schema_migrations','test_items','idx_test_items_name') ORDER BY type,name")
	if err != nil {
		return s, err
	}
	defer schemaRows.Close()
	for schemaRows.Next() {
		var typ, name, sqlText string
		if err := schemaRows.Scan(&typ, &name, &sqlText); err != nil {
			return s, err
		}
		s.schema = append(s.schema, map[string]string{"type": typ, "name": name, "sql": sqlText})
	}
	if err := schemaRows.Err(); err != nil {
		return s, err
	}
	dataRows, err := db.QueryContext(ctx, "SELECT id,name,created_at FROM test_items ORDER BY id")
	if err != nil {
		return s, err
	}
	defer dataRows.Close()
	for dataRows.Next() {
		var id, name, created string
		if err := dataRows.Scan(&id, &name, &created); err != nil {
			return s, err
		}
		s.data = append(s.data, map[string]any{"id": id, "name": name, "created_at": created})
	}
	if err := dataRows.Err(); err != nil {
		return s, err
	}
	if err := db.QueryRowContext(ctx, "SELECT 9007199254740993, NULL").Scan(&s.largeInteger, &s.nullValue); err != nil {
		return s, err
	}
	return s, nil
}

func rollbackCase() (observation, error) {
	d := mustTemp()
	defer os.RemoveAll(d)
	db, err := sqlitekit.Open(filepath.Join(d, "database.db"))
	if err != nil {
		return observation{}, err
	}
	defer db.Close()
	partialBad := fstestFS(map[string]string{
		"migrations/001_first.sql":  "CREATE TABLE first_probe (id INTEGER PRIMARY KEY, value TEXT); INSERT INTO first_probe VALUES (1, 'kept');",
		"migrations/002_second.sql": "CREATE TABLE second_probe (id INTEGER); THIS IS NOT VALID SQL;",
	})
	partialErr := sqlitekit.Migrate(db, partialBad)
	var kept, firstVersion string
	if err := db.QueryRow("SELECT value FROM first_probe WHERE id=1").Scan(&kept); err != nil {
		return observation{}, err
	}
	if err := db.QueryRow("SELECT version FROM schema_migrations ORDER BY version").Scan(&firstVersion); err != nil {
		return observation{}, err
	}
	failedVersionAbsent := errors.Is(db.QueryRow("SELECT version FROM schema_migrations WHERE version='002_second'").Scan(new(string)), sql.ErrNoRows)
	partialGood := fstestFS(map[string]string{
		"migrations/001_first.sql":  "THIS REPLACEMENT MUST NOT RUN;",
		"migrations/002_second.sql": "CREATE TABLE second_probe (id INTEGER); INSERT INTO second_probe VALUES (2);",
	})
	rerunErr := sqlitekit.Migrate(db, partialGood)
	var secondCount int
	if err := db.QueryRow("SELECT COUNT(*) FROM second_probe").Scan(&secondCount); err != nil {
		return observation{}, err
	}
	var keptAfter, firstVersionAfter string
	if err := db.QueryRow("SELECT value FROM first_probe WHERE id=1").Scan(&keptAfter); err != nil {
		return observation{}, err
	}
	if err := db.QueryRow("SELECT version FROM schema_migrations WHERE version='001_first'").Scan(&firstVersionAfter); err != nil {
		return observation{}, err
	}
	partialState := map[string]any{"first_table_unchanged": keptAfter == kept, "first_version_unchanged": firstVersionAfter == firstVersion, "first_data_unchanged": keptAfter == kept, "failed_version_absent": failedVersionAbsent, "rerun_succeeded": rerunErr == nil, "second_rows": secondCount}
	bad := fstestFS(map[string]string{"migrations/001_partial.sql": "CREATE TABLE rollback_probe (id INTEGER);\nTHIS IS NOT VALID SQL;"})
	execErr := sqlitekit.Migrate(db, bad)
	rollbackProbeAbsent := errors.Is(db.QueryRow("SELECT name FROM sqlite_master WHERE name='rollback_probe'").Scan(new(string)), sql.ErrNoRows)
	insertDB, err := sqlitekit.Open(filepath.Join(d, "insert.db"))
	if err != nil {
		return observation{}, err
	}
	defer insertDB.Close()
	if _, err := insertDB.Exec("CREATE TABLE versions_underlying (version TEXT, applied_at TEXT); CREATE VIEW schema_migrations AS SELECT version, applied_at FROM versions_underlying"); err != nil {
		return observation{}, err
	}
	insertErr := sqlitekit.Migrate(insertDB, migrations)
	insertAbsent := errors.Is(insertDB.QueryRow("SELECT name FROM sqlite_master WHERE name='test_items'").Scan(new(string)), sql.ErrNoRows)
	return observation{ID: "SQL-005", Success: partialErr != nil && rerunErr == nil && kept == "kept" && firstVersion == "001_first" && failedVersionAbsent && execErr != nil && insertErr != nil && rollbackProbeAbsent && insertAbsent, State: map[string]any{"rollback_probe_absent": rollbackProbeAbsent, "insert_migration_absent": insertAbsent, "partial_rerun": partialState}, Negative: []negative{negativeFrom("exec_failure", execErr, "failed to execute migration", rollbackProbeAbsent), negativeFrom("insert_failure", insertErr, "failed to record migration", insertAbsent)}}, nil
}

func errorCase() (observation, error) {
	d := mustTemp()
	defer os.RemoveAll(d)
	db, err := sqlitekit.Open(filepath.Join(d, "database.db"))
	if err != nil {
		return observation{}, err
	}
	db.Close()
	closedErr := sqlitekit.Migrate(db, migrations)
	missing, err := sqlitekit.Open(filepath.Join(d, "missing.db"))
	if err != nil {
		return observation{}, err
	}
	missingErr := sqlitekit.Migrate(missing, fstestFS(nil))
	missing.Close()
	version, err := sqlitekit.Open(filepath.Join(d, "version.db"))
	if err != nil {
		return observation{}, err
	}
	if _, err := version.Exec("CREATE VIEW schema_migrations AS SELECT 1 AS version, datetime('now') AS applied_at FROM missing_table"); err != nil {
		return observation{}, err
	}
	versionErr := sqlitekit.Migrate(version, migrations)
	version.Close()
	readDB, err := sqlitekit.Open(filepath.Join(d, "read.db"))
	if err != nil {
		return observation{}, err
	}
	readErr := sqlitekit.Migrate(readDB, readFileErrorFS{migrations})
	readDB.Close()
	mem, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		return observation{}, err
	}
	defer mem.Close()
	memErr := sqlitekit.Migrate(mem, migrations)
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	if memErr == nil {
		if _, err := mem.ExecContext(ctx, "INSERT INTO test_items (id,name) VALUES ('memory-1','in-memory')"); err != nil {
			return observation{}, err
		}
	}
	memState := map[string]any{"schema": []map[string]string{}, "data": []map[string]string{}}
	if memErr == nil {
		schema, data, err := memoryState(ctx, mem)
		if err != nil {
			return observation{}, err
		}
		memState["schema"] = schema
		memState["data"] = data
	}
	neg := []negative{negativeFrom("closed_db", closedErr, "failed to create schema_migrations table", false), negativeFrom("missing_directory", missingErr, "failed to read migrations directory", false), negativeFrom("version_query", versionErr, "failed to check migration state", false), negativeFrom("read_file", readErr, "failed to read migration", false)}
	return observation{ID: "SQL-006", Success: closedErr != nil && missingErr != nil && versionErr != nil && readErr != nil && memErr == nil && len(memState["schema"].([]map[string]string)) >= 2 && len(memState["data"].([]map[string]string)) == 1, State: map[string]any{"closed_error": errorString(closedErr), "missing_dir_error": errorString(missingErr), "version_query_error": errorString(versionErr), "read_file_error": errorString(readErr), "in_memory_success": memErr == nil, "in_memory": memState}, Negative: neg}, nil
}

func memoryState(ctx context.Context, db *sql.DB) ([]map[string]string, []map[string]string, error) {
	var schema []map[string]string
	rows, err := db.QueryContext(ctx, "SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")
	if err != nil {
		return nil, nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var typ, name, sqlText string
		if err := rows.Scan(&typ, &name, &sqlText); err != nil {
			return nil, nil, err
		}
		schema = append(schema, map[string]string{"type": typ, "name": name, "sql": sqlText})
	}
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}
	var data []map[string]string
	dataRows, err := db.QueryContext(ctx, "SELECT id,name FROM test_items ORDER BY id")
	if err != nil {
		return nil, nil, err
	}
	defer dataRows.Close()
	for dataRows.Next() {
		var id, name string
		if err := dataRows.Scan(&id, &name); err != nil {
			return nil, nil, err
		}
		data = append(data, map[string]string{"id": id, "name": name})
	}
	if err := dataRows.Err(); err != nil {
		return nil, nil, err
	}
	return schema, data, nil
}

func negativeFrom(name string, err error, contains string, rolledBack bool) negative {
	return negative{Name: name, Error: errorString(err), ErrorContains: contains, RolledBack: rolledBack, Cause: errorCause(err)}
}

func errorCause(err error) map[string]any {
	var coded interface{ Code() int }
	if errors.As(err, &coded) {
		return map[string]any{"type": "sqlite", "code": coded.Code() & 255}
	}
	if errors.Is(err, fs.ErrNotExist) {
		return map[string]any{"type": "io", "kind": "NotFound"}
	}
	if errors.Is(err, syscall.ENOTDIR) {
		return map[string]any{"type": "io", "kind": "NotADirectory"}
	}
	return map[string]any{"type": "unclassified"}
}
func errorString(err error) string {
	if err == nil {
		return ""
	}
	return err.Error()
}
func normalizeError(err error, root string) string {
	return strings.ReplaceAll(errorString(err), root, "<temp-root>")
}
func mustTemp() string {
	d, err := os.MkdirTemp("", "corekit-rust006-")
	if err != nil {
		fatal(err.Error())
	}
	return d
}
func fatal(s string) { _, _ = fmt.Fprintln(os.Stderr, s); os.Exit(2) }
func fstestFS(m map[string]string) fs.FS {
	f := fstest.MapFS{}
	for n, d := range m {
		f[n] = &fstest.MapFile{Data: []byte(d)}
	}
	return f
}

type readFileErrorFS struct{ fs.FS }

func (f readFileErrorFS) ReadFile(string) ([]byte, error) { return nil, os.ErrNotExist }

type countingFS struct {
	fs.FS
	reads int
}

func (f *countingFS) ReadFile(name string) ([]byte, error) {
	f.reads++
	return f.FS.(interface{ ReadFile(string) ([]byte, error) }).ReadFile(name)
}
