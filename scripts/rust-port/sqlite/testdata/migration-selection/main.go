// Observe filename selection through the pinned production sqlitekit.Migrate.
package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"runtime"
	"testing/fstest"

	"github.com/danieljustus/symaira-corekit/sqlitekit"
	_ "modernc.org/sqlite"
)

type entry struct {
	Name  string `json:"name"`
	IsDir bool   `json:"is_dir"`
	SQL   string `json:"sql"`
}

type scenario struct {
	ID      string  `json:"id"`
	Entries []entry `json:"entries"`
}

type tracedFS struct {
	fs.FS
	reads []string
}

func (f *tracedFS) ReadFile(name string) ([]byte, error) {
	f.reads = append(f.reads, name)
	return fs.ReadFile(f.FS, name)
}

func observe(c scenario) (map[string]any, error) {
	files := fstest.MapFS{}
	for _, e := range c.Entries {
		file := &fstest.MapFile{Data: []byte(e.SQL), Mode: 0600}
		if e.IsDir {
			file.Mode = fs.ModeDir | 0700
		}
		files["migrations/"+e.Name] = file
	}
	source := &tracedFS{FS: files, reads: []string{}}
	db, err := sql.Open("sqlite", ":memory:")
	if err != nil {
		return nil, err
	}
	defer db.Close()
	db.SetMaxOpenConns(1)
	if err := sqlitekit.Migrate(db, source); err != nil {
		return nil, err
	}
	versions := []string{}
	rows, err := db.Query("SELECT version FROM schema_migrations ORDER BY version")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var version string
		if err := rows.Scan(&version); err != nil {
			rows.Close()
			return nil, err
		}
		versions = append(versions, version)
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	schema := []map[string]string{}
	rows, err = db.Query("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")
	if err != nil {
		return nil, err
	}
	for rows.Next() {
		var kind, name, statement string
		if err := rows.Scan(&kind, &name, &statement); err != nil {
			rows.Close()
			return nil, err
		}
		schema = append(schema, map[string]string{"type": kind, "name": name, "sql": statement})
	}
	if err := rows.Close(); err != nil {
		return nil, err
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	data := []map[string]any{}
	rows, err = db.Query("SELECT id,value FROM selection ORDER BY id")
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var id int64
		var value string
		if err := rows.Scan(&id, &value); err != nil {
			return nil, err
		}
		data = append(data, map[string]any{"id": id, "value": value})
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return map[string]any{"id": c.ID, "reads": source.reads, "versions": versions, "schema": schema, "data": data}, nil
}

func run() error {
	if len(os.Args) != 2 {
		return fmt.Errorf("expected one neutral case manifest")
	}
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		return err
	}
	var input struct {
		Cases []scenario `json:"cases"`
	}
	if err := json.Unmarshal(raw, &input); err != nil {
		return err
	}
	observed := []map[string]any{}
	for _, c := range input.Cases {
		state, err := observe(c)
		if err != nil {
			return err
		}
		observed = append(observed, state)
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"go_version": runtime.Version(), "cases": observed})
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
