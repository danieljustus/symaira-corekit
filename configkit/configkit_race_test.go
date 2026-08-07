package configkit

import (
	"sync"
	"testing"
)

// TestLoaderConcurrent hammers Load/Reload/ResetCache from parallel
// goroutines. Before Loader guarded its cache with a mutex this tripped the
// race detector on cached/cachedErr/once; it must pass cleanly under -race.
func TestLoaderConcurrent(t *testing.T) {
	t.Setenv("RACELOAD_NAME", "race-config")

	// Unique app name: no ~/.config/{name}/config.toml and no ./{name}.toml
	// exist, so the loader stays hermetic and always succeeds with defaults
	// plus the env override below.
	loader := NewLoader(Options{AppName: "configkit-race-nodir-xyz", EnvPrefix: "RACELOAD"}, testDefaults)

	const goroutines = 8
	const iterations = 200

	var wg sync.WaitGroup
	wg.Add(goroutines)
	for g := 0; g < goroutines; g++ {
		go func(g int) {
			defer wg.Done()
			for i := 0; i < iterations; i++ {
				switch (g + i) % 3 {
				case 0:
					cfg, err := loader.Load()
					if err != nil {
						t.Errorf("Load() error = %v", err)
						return
					}
					if cfg == nil {
						t.Error("Load() returned nil config")
						return
					}
				case 1:
					if _, err := loader.Reload(); err != nil {
						t.Errorf("Reload() error = %v", err)
						return
					}
				case 2:
					loader.ResetCache()
				}
			}
		}(g)
	}
	wg.Wait()

	// After the dust settles the loader must still produce a valid config.
	cfg, err := loader.Load()
	if err != nil {
		t.Fatalf("final Load() error = %v", err)
	}
	if cfg == nil {
		t.Fatal("final Load() returned nil config")
	}
	if cfg.Name != "race-config" {
		t.Errorf("final Load() Name = %q, want %q", cfg.Name, "race-config")
	}
}
