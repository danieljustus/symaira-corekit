package updateapply

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/danieljustus/symaira-corekit/updatecheck"
)

func TestCancelledDownloadClosesBeforeRemovingStagingFile(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", "100")
		if _, err := w.Write([]byte("partial")); err != nil {
			t.Error(err)
			return
		}
		w.(http.Flusher).Flush()
		<-r.Context().Done()
	}))
	defer server.Close()
	directory := t.TempDir()
	target := filepath.Join(directory, "old-binary")
	if err := os.WriteFile(target, []byte("old"), 0600); err != nil {
		t.Fatal(err)
	}
	a := NewApplier()
	a.Progress = func(_, _ int64) { cancel() }
	_, _, err := a.downloadToTemp(ctx, directory, updatecheck.Asset{
		Name: "fixture", BrowserDownloadURL: server.URL,
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected cancelled download, got %v", err)
	}
	entries, err := os.ReadDir(directory)
	if err != nil {
		t.Fatal(err)
	}
	if len(entries) != 1 || entries[0].Name() != "old-binary" {
		t.Fatalf("failed download left staging residue: %v", entries)
	}
	data, err := os.ReadFile(target)
	if err != nil || string(data) != "old" {
		t.Fatalf("previous binary changed: %q, %v", data, err)
	}
}
