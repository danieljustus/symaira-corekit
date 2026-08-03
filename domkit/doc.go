// Package domkit provides the shared semantic DOM pipeline for the Symaira
// fetch/browse family (issue X-3): HTML→Markdown rendering, outline
// extraction, output schema, truncation and content-boundary markers.
//
// The package is the extracted common core of the former
// internal/render implementations in symaira-browse and symaira-fetch and
// stays free of browser- and fingerprint-specific code.
package domkit
