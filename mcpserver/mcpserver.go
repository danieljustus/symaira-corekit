// Package mcpserver provides a JSON-RPC 2.0 server framework for the Model
// Context Protocol (MCP). It implements the MCP stdio transport with
// Content-Length framing and exposes a registration-based API so that
// consumers can define tools without coupling to the protocol layer.
package mcpserver

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"os"
	"strconv"
	"strings"
)

const ProtocolVersion = "2024-11-05"

// maxLineBytes bounds a single newline-delimited line (a header line or a
// line-mode JSON message). It matches the 1 MiB cap on framed message bodies so
// a peer cannot cause unbounded buffering by sending data without a newline.
const maxLineBytes = 1 << 20

const (
	CodeParseError     = -32700
	CodeInvalidRequest = -32600
	CodeMethodNotFound = -32601
	CodeInvalidParams  = -32602
	CodeInternalError  = -32603
)

const fallbackError = `{"jsonrpc":"2.0","id":null,"error":{"code":-32603,"message":"internal error: failed to marshal response"}}`

type jsonParseError struct {
	msg  string
	mode responseMode
}

func (e *jsonParseError) Error() string { return e.msg }

type responseMode int

const (
	responseModeFramed responseMode = iota
	responseModeLine
)

type responseWriter struct {
	w    io.Writer
	mode responseMode
}

// ToolAnnotations carries optional MCP tool-behaviour hints that are
// serialised as the standard "annotations" field in tools/list. These are
// client-facing advisory hints, not Guard-style enforcement. A nil/zero
// value omits the field entirely from the protocol response.
type ToolAnnotations struct {
	// Title is a human-readable title for the tool.
	Title string `json:"title,omitempty"`

	// ReadOnlyHint, when true, tells the client that this tool performs no
	// side-effect state changes.
	ReadOnlyHint bool `json:"readOnlyHint,omitempty"`

	// IdempotentHint, when true, tells the client that calling this tool
	// repeatedly with the same arguments produces the same result.
	IdempotentHint bool `json:"idempotentHint,omitempty"`

	// OpenWorldHint, when true, tells the client that this tool may
	// interact with external entities outside the MCP server's control.
	OpenWorldHint bool `json:"openWorldHint,omitempty"`

	// DestructiveHint, when true, tells the client that this tool may
	// perform destructive updates (deletes, overwrites, etc.).
	DestructiveHint bool `json:"destructiveHint,omitempty"`
}

// ContentBlock is one MCP tool-result content item. It intentionally accepts
// arbitrary JSON fields so consumers can return text, image, audio,
// resource-link, or embedded-resource blocks without the corekit needing to
// model every MCP content variant.
type ContentBlock map[string]any

// ToolResult is the optional typed result a tool handler can return. Returning
// ToolResult preserves content blocks and structured content on the wire;
// returning any other value keeps the legacy single-text-block behaviour.
type ToolResult struct {
	Content           []ContentBlock `json:"content"`
	StructuredContent any            `json:"structuredContent,omitempty"`
	Meta              map[string]any `json:"_meta,omitempty"`
}

// requestMetaKey is private so callers can only access request metadata via
// RequestMeta, preventing collisions with consumer context values.
type requestMetaKey struct{}

// RequestMeta returns the optional _meta object supplied with tools/call. The
// second result is false when the request did not include metadata.
func RequestMeta(ctx context.Context) (map[string]any, bool) {
	meta, ok := ctx.Value(requestMetaKey{}).(map[string]any)
	return meta, ok
}

// Tool defines a MCP tool that can be called by clients.
type Tool struct {
	Name        string
	Description string
	InputSchema json.RawMessage

	// Annotations carries optional MCP tool-behaviour hints. When nil or
	// all-zero, no "annotations" field is emitted in tools/list.
	Annotations *ToolAnnotations

	// Handler is invoked when the client calls this tool. input is the raw JSON
	// "arguments" object from the tools/call request. The returned value is
	// marshalled as the tool result; if err is non-nil the server sends a tool
	// error response instead.
	Handler func(ctx context.Context, input json.RawMessage) (any, error)
}

type jsonRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      any             `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
	HasID   bool            `json:"-"`
}

// UnmarshalJSON records whether the request included an id. JSON-RPC
// notifications omit the id member; that is distinct from a request that
// explicitly sends a null id.
func (r *jsonRPCRequest) UnmarshalJSON(data []byte) error {
	type requestAlias jsonRPCRequest
	var parsed requestAlias
	if err := json.Unmarshal(data, &parsed); err != nil {
		return err
	}
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(data, &fields); err != nil {
		return err
	}
	*r = jsonRPCRequest(parsed)
	_, r.HasID = fields["id"]
	return nil
}

type jsonRPCResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID      any    `json:"id"`
	Result  any    `json:"result,omitempty"`
	Error   any    `json:"error,omitempty"`
}

// Server is a JSON-RPC 2.0 MCP server that dispatches to registered tools.
type Server struct {
	name         string
	version      string
	instructions string
	tools        map[string]*Tool
	order        []string
}

// New creates a new MCP server.
func New(name, version string) *Server {
	return &Server{
		name:    name,
		version: version,
		tools:   make(map[string]*Tool),
	}
}

// SetInstructions sets the server-level usage guidance returned to clients in
// the "instructions" field of the initialize response. MCP clients typically
// surface this text to the model as system context, so it is the primary lever
// for telling agents when and how to use the server's tools. An empty string
// (the default) omits the field entirely.
func (s *Server) SetInstructions(text string) {
	s.instructions = text
}

// RegisterTool adds a tool to the server. Panics on duplicate names.
func (s *Server) RegisterTool(t *Tool) {
	if t == nil {
		panic("mcpserver: RegisterTool called with nil Tool")
	}
	if t.Name == "" {
		panic("mcpserver: RegisterTool called with empty Name")
	}
	if _, exists := s.tools[t.Name]; exists {
		panic("mcpserver: duplicate tool registration: " + t.Name)
	}
	s.tools[t.Name] = t
	s.order = append(s.order, t.Name)
}

// ServeStdio runs the server on os.Stdin/os.Stdout. All logging goes to
// os.Stderr to avoid polluting the JSON-RPC transport.
func (s *Server) ServeStdio(ctx context.Context) error {
	return s.ServeIO(ctx, os.Stdin, os.Stdout)
}

// ServeIO runs the server on the given reader and writer. This method is the
// primary entry point for testing.
func (s *Server) ServeIO(ctx context.Context, r io.Reader, w io.Writer) error {
	br := bufio.NewReader(r)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}

		req, mode, err := readRequest(br)
		if err != nil {
			if err == io.EOF {
				return nil
			}
			var pe *jsonParseError
			if errors.As(err, &pe) {
				sendError(responseWriter{w: w, mode: pe.mode}, nil, CodeParseError, "Parse error: "+pe.msg)
				continue
			}
			return fmt.Errorf("mcpserver: read error: %w", err)
		}

		s.handleRequest(ctx, responseWriter{w: w, mode: mode}, req)
	}
}

// readRequest reads a single JSON-RPC request from either a Content-Length
// framed stream or a newline-delimited JSON stream. Framed messages are
// preceded by headers of the form:
//
//	Content-Length: <n>\r\n
//	\r\n
//	<json bytes of length n>
func readRequest(br *bufio.Reader) (*jsonRPCRequest, responseMode, error) {
	line, err := readNonEmptyLine(br)
	if err != nil {
		return nil, responseModeFramed, err
	}

	if strings.HasPrefix(line, "{") || !strings.Contains(line, ":") {
		return parseLineRequest(line)
	}

	var contentLength int
	found := false
	if rest, ok := strings.CutPrefix(line, "Content-Length:"); ok {
		val := strings.TrimSpace(rest)
		n, err := strconv.Atoi(val)
		if err != nil {
			return nil, responseModeFramed, fmt.Errorf("invalid Content-Length: %q", val)
		}
		contentLength = n
		found = true
	}

	for {
		line, err := readLineLimited(br)
		if err != nil {
			return nil, responseModeFramed, err
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			break
		}
		if rest, ok := strings.CutPrefix(line, "Content-Length:"); ok {
			val := strings.TrimSpace(rest)
			n, err := strconv.Atoi(val)
			if err != nil {
				return nil, responseModeFramed, fmt.Errorf("invalid Content-Length: %q", val)
			}
			contentLength = n
			found = true
		}
	}
	if !found {
		return nil, responseModeFramed, fmt.Errorf("missing Content-Length header")
	}
	if contentLength <= 0 || contentLength > 1<<20 {
		return nil, responseModeFramed, fmt.Errorf("invalid Content-Length: %d", contentLength)
	}

	body := make([]byte, contentLength)
	if _, err := io.ReadFull(br, body); err != nil {
		return nil, responseModeFramed, fmt.Errorf("read body: %w", err)
	}

	var req jsonRPCRequest
	if err := json.Unmarshal(body, &req); err != nil {
		return nil, responseModeFramed, &jsonParseError{msg: err.Error(), mode: responseModeFramed}
	}
	return &req, responseModeFramed, nil
}

func readNonEmptyLine(br *bufio.Reader) (string, error) {
	for {
		line, err := readLineLimited(br)
		if err != nil {
			if err == io.EOF && line != "" {
				return strings.TrimSpace(line), nil
			}
			return "", err
		}

		line = strings.TrimSpace(line)
		if line != "" {
			return line, nil
		}
	}
}

// readLineLimited reads a single '\n'-terminated line from br, including the
// trailing newline, and returns an error if the line would exceed maxLineBytes.
// On EOF it returns whatever was read so far together with io.EOF, matching
// bufio.Reader.ReadString semantics.
func readLineLimited(br *bufio.Reader) (string, error) {
	var buf []byte
	for {
		chunk, err := br.ReadSlice('\n')
		if len(buf)+len(chunk) > maxLineBytes {
			return "", fmt.Errorf("line exceeds %d bytes", maxLineBytes)
		}
		buf = append(buf, chunk...)
		if err == nil {
			return string(buf), nil
		}
		if err == bufio.ErrBufferFull {
			continue
		}
		return string(buf), err
	}
}

func parseLineRequest(line string) (*jsonRPCRequest, responseMode, error) {
	var req jsonRPCRequest
	if err := json.Unmarshal([]byte(line), &req); err != nil {
		return nil, responseModeLine, &jsonParseError{msg: err.Error(), mode: responseModeLine}
	}
	return &req, responseModeLine, nil
}

func writeResponse(rw responseWriter, resp jsonRPCResponse) {
	data, err := json.Marshal(resp)
	if err != nil {
		slog.Error("mcpserver: failed to marshal JSON-RPC response", "err", err)
		writeBytes(rw, []byte(fallbackError))
		return
	}
	writeBytes(rw, data)
}

func writeBytes(rw responseWriter, data []byte) {
	if rw.mode == responseModeLine {
		fmt.Fprintf(rw.w, "%s\n", data)
		return
	}
	fmt.Fprintf(rw.w, "Content-Length: %d\r\n\r\n%s", len(data), data)
}

func (s *Server) handleRequest(ctx context.Context, w responseWriter, req *jsonRPCRequest) {
	defer func() {
		if r := recover(); r != nil {
			slog.Error("mcpserver: handler panicked", "method", req.Method, "panic", r)
			sendError(w, req.ID, CodeInternalError, "Internal error: handler panicked")
		}
	}()

	// JSON-RPC notifications have no id and never receive a response,
	// including when the method is unknown. This check must happen before
	// dispatch so notification methods can grow without producing errors.
	if !req.HasID && req.ID == nil {
		return
	}

	switch req.Method {
	case "initialize":
		s.handleInitialize(w, req)
	case "ping":
		sendResponse(w, req.ID, map[string]any{})
	case "tools/list":
		s.handleToolsList(w, req)
	case "tools/call":
		s.handleToolsCall(ctx, w, req)
	default:
		sendError(w, req.ID, CodeMethodNotFound, "Method not found: "+req.Method)
	}
}

func (s *Server) handleInitialize(w responseWriter, req *jsonRPCRequest) {
	result := map[string]any{
		"protocolVersion": ProtocolVersion,
		"capabilities": map[string]any{
			"tools": map[string]any{},
		},
		"serverInfo": map[string]string{
			"name":    s.name,
			"version": s.version,
		},
	}
	if s.instructions != "" {
		result["instructions"] = s.instructions
	}
	sendResponse(w, req.ID, result)
}

func (s *Server) handleToolsList(w responseWriter, req *jsonRPCRequest) {
	tools := make([]map[string]any, 0, len(s.order))
	for _, name := range s.order {
		t := s.tools[name]
		tool := map[string]any{
			"name":        t.Name,
			"description": t.Description,
		}
		if t.InputSchema != nil {
			var schema any
			if err := json.Unmarshal(t.InputSchema, &schema); err == nil {
				tool["inputSchema"] = schema
			} else {
				tool["inputSchema"] = json.RawMessage(t.InputSchema)
			}
		}
		if t.Annotations != nil {
			tool["annotations"] = t.Annotations
		}
		tools = append(tools, tool)
	}
	sendResponse(w, req.ID, map[string]any{
		"tools": tools,
	})
}

func (s *Server) handleToolsCall(ctx context.Context, w responseWriter, req *jsonRPCRequest) {
	var params struct {
		Name      string          `json:"name"`
		Arguments json.RawMessage `json:"arguments"`
		Meta      map[string]any  `json:"_meta,omitempty"`
	}
	if err := json.Unmarshal(req.Params, &params); err != nil {
		sendError(w, req.ID, CodeInvalidParams, "Invalid params: "+err.Error())
		return
	}

	tool, ok := s.tools[params.Name]
	if !ok {
		sendError(w, req.ID, CodeMethodNotFound, "Unknown tool: "+params.Name)
		return
	}

	if tool.Handler == nil {
		sendError(w, req.ID, CodeInternalError, "Tool has no handler: "+params.Name)
		return
	}

	if params.Meta != nil {
		ctx = context.WithValue(ctx, requestMetaKey{}, params.Meta)
	}
	result, err := tool.Handler(ctx, params.Arguments)
	if err != nil {
		sendToolError(w, req.ID, err.Error())
		return
	}

	if typed, ok := result.(ToolResult); ok {
		sendToolResponse(w, req.ID, typed)
		return
	}
	if typed, ok := result.(*ToolResult); ok && typed != nil {
		sendToolResponse(w, req.ID, *typed)
		return
	}

	data, err := json.Marshal(result)
	if err != nil {
		sendToolError(w, req.ID, "Failed to marshal tool result: "+err.Error())
		return
	}
	sendToolResponseRaw(w, req.ID, data)
}

func sendResponse(w responseWriter, id any, result any) {
	writeResponse(w, jsonRPCResponse{JSONRPC: "2.0", ID: id, Result: result})
}

func sendToolResponse(w responseWriter, id any, result ToolResult) {
	content := result.Content
	if content == nil {
		content = []ContentBlock{}
	}
	toolResult := map[string]any{
		"content": content,
		"isError": false,
	}
	if result.StructuredContent != nil {
		toolResult["structuredContent"] = result.StructuredContent
	}
	if result.Meta != nil {
		toolResult["_meta"] = result.Meta
	}
	writeResponse(w, jsonRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Result:  toolResult,
	})
}

func sendToolResponseRaw(w responseWriter, id any, raw json.RawMessage) {
	// raw is the JSON-marshalled handler return value. MCP TextContent.text
	// must be a JSON string, so we convert any non-string JSON (maps,
	// slices, scalars) to its string representation. This keeps the
	// existing correct behaviour for string-typed handler returns while
	// fixing the schema violation for structured results.
	var text string
	if len(raw) > 0 && raw[0] == '"' {
		// raw is already a JSON string — extract the Go string value.
		if err := json.Unmarshal(raw, &text); err != nil {
			text = string(raw)
		}
	} else {
		text = string(raw)
	}
	writeResponse(w, jsonRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Result: map[string]any{
			"content": []map[string]any{
				{"type": "text", "text": text},
			},
			"isError": false,
		},
	})
}

func sendToolError(w responseWriter, id any, text string) {
	sendResponse(w, id, map[string]any{
		"content": []map[string]any{
			{"type": "text", "text": text},
		},
		"isError": true,
	})
}

func sendError(w responseWriter, id any, code int, message string) {
	writeResponse(w, jsonRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error: map[string]any{
			"code":    code,
			"message": message,
		},
	})
}
