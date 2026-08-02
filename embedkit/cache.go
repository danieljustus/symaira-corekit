package embedkit

import (
	"container/list"
	"sync"
)

// Cache stores embedding results by lookup key using a bounded least-recently
// used (LRU) policy. Cache is safe for concurrent use.
//
// A key is typically the input text or a stable digest of it. The cache does
// not interpret keys, so callers can choose the keying scheme that fits their
// embedding pipeline.
type Cache struct {
	capacity int

	mu      sync.Mutex
	entries map[string]*list.Element
	order   *list.List
}

type cacheEntry struct {
	key    string
	result Result
}

// NewCache returns an embedding result cache with capacity entries. A
// non-positive capacity creates a disabled cache: Set is a no-op and Get
// always reports a miss.
func NewCache(capacity int) *Cache {
	if capacity < 0 {
		capacity = 0
	}
	return &Cache{
		capacity: capacity,
		entries:  make(map[string]*list.Element),
		order:    list.New(),
	}
}

// Get returns the result stored for key and marks it as recently used. The
// returned Result owns its vector slice; changing it does not mutate the
// cached value.
func (c *Cache) Get(key string) (Result, bool) {
	if c == nil {
		return Result{}, false
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	element, ok := c.entries[key]
	if !ok {
		return Result{}, false
	}
	c.order.MoveToFront(element)
	return cloneResult(element.Value.(*cacheEntry).result), true
}

// Set stores result for key and marks the entry as recently used. If key is
// already cached, its value is replaced without increasing the cache size.
// When the cache is full, the least recently used entry is evicted.
func (c *Cache) Set(key string, result Result) {
	if c == nil {
		return
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	if c.capacity <= 0 {
		return
	}
	c.initLocked()

	if element, ok := c.entries[key]; ok {
		element.Value.(*cacheEntry).result = cloneResult(result)
		c.order.MoveToFront(element)
		return
	}

	if c.order.Len() >= c.capacity {
		oldest := c.order.Back()
		if oldest != nil {
			entry := oldest.Value.(*cacheEntry)
			delete(c.entries, entry.key)
			c.order.Remove(oldest)
		}
	}

	element := c.order.PushFront(&cacheEntry{
		key:    key,
		result: cloneResult(result),
	})
	c.entries[key] = element
}

// Len returns the number of results currently stored in the cache.
func (c *Cache) Len() int {
	if c == nil {
		return 0
	}

	c.mu.Lock()
	defer c.mu.Unlock()
	return len(c.entries)
}

func (c *Cache) initLocked() {
	if c.entries == nil {
		c.entries = make(map[string]*list.Element)
	}
	if c.order == nil {
		c.order = list.New()
	}
}

func cloneResult(result Result) Result {
	if result.Vector != nil {
		result.Vector = append([]float32(nil), result.Vector...)
	}
	return result
}
