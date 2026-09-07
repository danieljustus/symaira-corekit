# ADR RUST-002: Process environment deletion

- **Decision:** keep the safe `Environment` map as the default abstraction and
  expose process-global deletion only as `unsafe fn unsetenv`.
- **Reason:** Rust 2024 makes `std::env::remove_var` unsafe because arbitrary
  readers and foreign threads can race process-environment mutation. Go's
  `envutil.Unsetenv` is retained as a parity seam, but making it safe in Rust
  would claim synchronization that the process environment does not provide.
- **Caller contract:** the unsafe caller must establish exclusive access to
  process environment reads and writes for the duration of the call. The
  function validates names and delegates directly to `remove_var`; it does not
  provide a safe wrapper or a process-wide lock.
- **Verification:** `ENV-002` uses the Go-generated fixture and a focused Rust
  test for both the safe map operation and the explicit unsafe process seam.
