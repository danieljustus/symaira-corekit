package embedkit

import (
	"strconv"
	"sync"
	"testing"
)

func TestCacheHitReturnsStoredResult(t *testing.T) {
	cache := NewCache(2)
	want := Result{
		Vector: []float32{1, 2, 3},
		Source: "ollama",
		Model:  "qwen3-embedding:0.6b",
		Dim:    3,
		Quant:  "4bit-mlx",
	}

	cache.Set("hello", want)
	got, ok := cache.Get("hello")
	if !ok {
		t.Fatal("Get returned a miss for a cached key")
	}
	if got.Source != want.Source || got.Model != want.Model || got.Dim != want.Dim || got.Quant != want.Quant {
		t.Fatalf("Get returned metadata %+v, want %+v", got, want)
	}
	if len(got.Vector) != len(want.Vector) {
		t.Fatalf("Get returned vector length %d, want %d", len(got.Vector), len(want.Vector))
	}
	for i := range want.Vector {
		if got.Vector[i] != want.Vector[i] {
			t.Fatalf("Get returned vector[%d] = %v, want %v", i, got.Vector[i], want.Vector[i])
		}
	}

	// Results are copied on the cache boundary so callers cannot mutate a
	// cached vector through either the value passed to Set or Get's return.
	want.Vector[0] = 99
	got.Vector[1] = 99
	again, ok := cache.Get("hello")
	if !ok {
		t.Fatal("second Get returned a miss for a cached key")
	}
	if again.Vector[0] != 1 || again.Vector[1] != 2 {
		t.Fatalf("cached vector was mutated through a caller: %v", again.Vector)
	}
}

func TestCacheLRUEviction(t *testing.T) {
	cache := NewCache(2)
	cache.Set("first", Result{Model: "one"})
	cache.Set("second", Result{Model: "two"})

	// Reading first makes second the least recently used entry.
	if _, ok := cache.Get("first"); !ok {
		t.Fatal("expected first to be cached")
	}
	cache.Set("third", Result{Model: "three"})

	if _, ok := cache.Get("second"); ok {
		t.Fatal("expected least recently used entry second to be evicted")
	}
	if got, ok := cache.Get("first"); !ok || got.Model != "one" {
		t.Fatalf("expected first to survive eviction, got %+v, ok=%v", got, ok)
	}
	if got, ok := cache.Get("third"); !ok || got.Model != "three" {
		t.Fatalf("expected third to be cached, got %+v, ok=%v", got, ok)
	}
	if got := cache.Len(); got != 2 {
		t.Fatalf("Len = %d after eviction, want 2", got)
	}
}

func TestCacheSetExistingKeyRefreshesAndReplaces(t *testing.T) {
	cache := NewCache(2)
	cache.Set("first", Result{Model: "old"})
	cache.Set("second", Result{Model: "two"})
	cache.Set("first", Result{Model: "new"})
	cache.Set("third", Result{Model: "three"})

	if _, ok := cache.Get("second"); ok {
		t.Fatal("expected second to be evicted after refreshing first")
	}
	if got, ok := cache.Get("first"); !ok || got.Model != "new" {
		t.Fatalf("expected replacement value for first, got %+v, ok=%v", got, ok)
	}
}

func TestCacheNonPositiveCapacityDisablesCaching(t *testing.T) {
	for _, capacity := range []int{0, -1} {
		t.Run("capacity="+strconv.Itoa(capacity), func(t *testing.T) {
			cache := NewCache(capacity)
			cache.Set("key", Result{Model: "model"})
			if _, ok := cache.Get("key"); ok {
				t.Fatal("disabled cache returned a hit")
			}
			if got := cache.Len(); got != 0 {
				t.Fatalf("Len = %d for disabled cache, want 0", got)
			}
		})
	}
}

func TestCacheConcurrentAccess(t *testing.T) {
	cache := NewCache(16)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func(worker int) {
			defer wg.Done()
			for j := 0; j < 100; j++ {
				key := strconv.Itoa(worker) + ":" + strconv.Itoa(j)
				cache.Set(key, Result{Vector: []float32{float32(j)}, Dim: 1})
				_, _ = cache.Get(key)
				_ = cache.Len()
			}
		}(i)
	}
	wg.Wait()

	if got := cache.Len(); got > 16 {
		t.Fatalf("Len = %d, exceeds capacity 16", got)
	}
}
