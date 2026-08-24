package sqlitekit_test

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/danieljustus/symaira-corekit/sqlitekit"
	_ "modernc.org/sqlite"
)

// ExampleOpen demonstrates opening a SQLite database and performing basic
// CRUD operations through the standard database/sql interface.
func ExampleOpen() {
	// Open creates the database directory if needed and configures WAL mode,
	// busy_timeout, and foreign_keys on every pooled connection.
	dir, _ := os.MkdirTemp("", "sqlitekit-example")
	defer os.RemoveAll(dir)

	db, err := sqlitekit.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		fmt.Printf("open error: %v\n", err)
		return
	}
	defer db.Close()

	_, _ = db.Exec("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
	_, _ = db.Exec("INSERT INTO items (name) VALUES (?)", "hello")

	var name string
	_ = db.QueryRow("SELECT name FROM items WHERE id = 1").Scan(&name)
	fmt.Println(name)
	// Output: hello
}
