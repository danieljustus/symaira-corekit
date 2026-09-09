package main

import (
	"strings"
	"testing"
)

func TestRun_SQLCaseCardinalityAndNegativeControls(t *testing.T) {
	r, err := run()
	if err != nil {
		t.Fatal(err)
	}
	if len(r.Cases) != 6 {
		t.Fatalf("case count = %d, want 6", len(r.Cases))
	}
	want := []string{"SQL-001", "SQL-002", "SQL-003", "SQL-004", "SQL-005", "SQL-006"}
	for i, c := range r.Cases {
		if c.ID != want[i] || !c.Success {
			t.Fatalf("case %d = %#v", i, c)
		}
		for _, n := range c.Negative {
			if n.Error == "" || n.ErrorContains == "" || !strings.Contains(n.Error, n.ErrorContains) {
				t.Errorf("%s/%s lost full error: %#v", c.ID, n.Name, n)
			}
		}
	}
}

func TestOpenCase_RecordsNativeModesAndFailures(t *testing.T) {
	c, err := openCase()
	if err != nil {
		t.Fatal(err)
	}
	if !c.Success {
		t.Fatalf("open case failed: %#v", c)
	}
	if c.State["native_goos"] == "" || c.State["native_goarch"] == "" {
		t.Fatalf("missing native mode: %#v", c.State)
	}
	errs := c.State["open_errors"].(map[string]string)
	for _, name := range []string{"missing_directory", "parent_file"} {
		if errs[name] == "" || strings.Contains(errs[name], "corekit-rust006-") {
			t.Errorf("%s error = %q", name, errs[name])
		}
	}
}

func TestPragmaCase_ContentionIncludesWALReaderAndTransactionResults(t *testing.T) {
	c, err := pragmaCase()
	if err != nil {
		t.Fatal(err)
	}
	lock := c.State["contention"].(map[string]any)
	for _, key := range []string{"observed", "tx_exec_succeeded", "blocked", "reader_succeeded", "rollback_succeeded", "within_busy_timeout"} {
		if lock[key] != true {
			t.Errorf("contention[%q] = %#v", key, lock[key])
		}
	}
}

func TestMigrationCases_ExposeSchemaDataAndUTCApplicationTimes(t *testing.T) {
	for _, repeated := range []bool{false, true} {
		c, err := migrateObserved("test", repeated)
		if err != nil {
			t.Fatal(err)
		}
		if !c.Success {
			t.Fatalf("repeated=%t: %#v", repeated, c)
		}
		if len(c.State["schema"].([]map[string]string)) != 3 {
			t.Fatalf("schema = %#v", c.State["schema"])
		}
		if len(c.State["data"].([]map[string]any)) != 1 {
			t.Fatalf("data = %#v", c.State["data"])
		}
		if c.State["applied_at_utc"] != true {
			t.Fatalf("applied_at_utc = %#v", c.State["applied_at_utc"])
		}
		if repeated {
			for _, key := range []string{"replacement_error_nil", "rows_unchanged", "versions_unchanged", "schema_unchanged"} {
				if c.State[key] != true {
					t.Errorf("%s = %#v", key, c.State[key])
				}
			}
			if c.State["replacement_read_attempts"] != 0 {
				t.Errorf("invalid applied file was read: %#v", c.State)
			}
		}
	}
}

func TestRollbackCase_ReportsBothFailedVersionsAbsent(t *testing.T) {
	c, err := rollbackCase()
	if err != nil {
		t.Fatal(err)
	}
	if !c.Success || c.State["rollback_probe_absent"] != true || c.State["insert_migration_absent"] != true {
		t.Fatalf("rollback = %#v", c)
	}
	if len(c.Negative) != 2 || c.Negative[0].Error == "" || c.Negative[1].Error == "" {
		t.Fatalf("negative errors = %#v", c.Negative)
	}
}

func TestErrorCase_InspectsInMemorySchemaAndData(t *testing.T) {
	c, err := errorCase()
	if err != nil {
		t.Fatal(err)
	}
	if !c.Success {
		t.Fatalf("errors = %#v", c)
	}
	mem := c.State["in_memory"].(map[string]any)
	if len(mem["schema"].([]map[string]string)) < 2 {
		t.Fatalf("memory schema = %#v", mem["schema"])
	}
	if len(mem["data"].([]map[string]string)) != 1 {
		t.Fatalf("memory data = %#v", mem["data"])
	}
}
