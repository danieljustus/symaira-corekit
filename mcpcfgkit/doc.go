// Package mcpcfgkit provides MCP server config discovery across AI client
// applications. It is the shared implementation behind symscope's mcpcfg,
// symguard's discovery, and symbrain's harness config handling: JSONC/JSON/
// YAML config parsing, client source enumeration, and a testable FS
// abstraction.
//
// Scope (deliberately narrow — no tool-specific logic):
//   - Client sources (Claude Desktop, Cursor, Windsurf, …) with env-aware
//     path resolution
//   - mcpServers config parsing from JSONC / JSON / YAML
//   - Server model with transport/command/args/env, ready for consumers to
//     enrich with tool-specific fields
//
// Standalone-first: this package imports no other Symaira module and depends
// only on the standard library + gopkg.in/yaml.v3.
package mcpcfgkit
