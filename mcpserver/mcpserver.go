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

const (
	CodeParseError     = -32700
	CodeInvalidRequest = -32600
	CodeMethodNotFound = -32601
	CodeInvalidParams  = -32602
	CodeInternalError  = -32603
)

const fallbackError = `{"jsonrpc":"2.0","id":null,"error":{"code":-32603,"message":"internal error: failed to marshal response"}}`

type jsonParseError struct {
	msg string
}

func (e *jsonParseError) Error() string { return e.msg }

// Tool defines a MCP tool that can be called by clients.
type Tool struct {
	Name        string
	Description string
	InputSchema json.RawMessage

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
}

type jsonRPCResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID      any    `json:"id"`
	Result  any    `json:"result,omitempty"`
	Error   any    `json:"error,omitempty"`
}

// Server is a JSON-RPC 2.0 MCP server that dispatches to registered tools.
type Server struct {
	name    string
	version string
	tools   map[string]*Tool
	order   []string
}

// New creates a new MCP server.
func New(name, version string) *Server {
	return &Server{
		name:    name,
		version: version,
		tools:   make(map[string]*Tool),
	}
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

		req, err := readRequest(br)
		if err != nil {
			if err == io.EOF {
				return nil
			}
			var pe *jsonParseError
			if errors.As(err, &pe) {
				sendError(w, nil, CodeParseError, "Parse error: "+pe.msg)
				continue
			}
			return fmt.Errorf("mcpserver: read error: %w", err)
		}

		s.handleRequest(ctx, w, req)
	}
}

// readRequest reads a single JSON-RPC request from a Content-Length framed
// stream. Each message is preceded by headers of the form:
//
//	Content-Length: <n>\r\n
//	\r\n
//	<json bytes of length n>
func readRequest(br *bufio.Reader) (*jsonRPCRequest, error) {
	var contentLength int
	found := false
	for {
		line, err := br.ReadString('\n')
		if err != nil {
			return nil, err
		}
		line = strings.TrimRight(line, "\r\n")
		if line == "" {
			break
		}
		if rest, ok := strings.CutPrefix(line, "Content-Length:"); ok {
			val := strings.TrimSpace(rest)
			n, err := strconv.Atoi(val)
			if err != nil {
				return nil, fmt.Errorf("invalid Content-Length: %q", val)
			}
			contentLength = n
			found = true
		}
	}
	if !found {
		return nil, fmt.Errorf("missing Content-Length header")
	}
	if contentLength <= 0 || contentLength > 1<<20 {
		return nil, fmt.Errorf("invalid Content-Length: %d", contentLength)
	}

	body := make([]byte, contentLength)
	if _, err := io.ReadFull(br, body); err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}

	var req jsonRPCRequest
	if err := json.Unmarshal(body, &req); err != nil {
		return nil, &jsonParseError{msg: err.Error()}
	}
	return &req, nil
}

func writeFrame(w io.Writer, resp jsonRPCResponse) {
	data, err := json.Marshal(resp)
	if err != nil {
		slog.Error("mcpserver: failed to marshal JSON-RPC response", "err", err)
		fmt.Fprintf(w, "Content-Length: %d\r\n\r\n%s", len(fallbackError), fallbackError)
		return
	}
	fmt.Fprintf(w, "Content-Length: %d\r\n\r\n%s", len(data), data)
}

func (s *Server) handleRequest(ctx context.Context, w io.Writer, req *jsonRPCRequest) {
	defer func() {
		if r := recover(); r != nil {
			slog.Error("mcpserver: handler panicked", "method", req.Method, "panic", r)
			sendError(w, req.ID, CodeInternalError, "Internal error: handler panicked")
		}
	}()

	switch req.Method {
	case "initialize":
		s.handleInitialize(w, req)
	case "notifications/initialized":
	case "tools/list":
		s.handleToolsList(w, req)
	case "tools/call":
		s.handleToolsCall(ctx, w, req)
	default:
		sendError(w, req.ID, CodeMethodNotFound, "Method not found: "+req.Method)
	}
}

func (s *Server) handleInitialize(w io.Writer, req *jsonRPCRequest) {
	sendResponse(w, req.ID, map[string]any{
		"protocolVersion": ProtocolVersion,
		"capabilities": map[string]any{
			"tools": map[string]any{},
		},
		"serverInfo": map[string]string{
			"name":    s.name,
			"version": s.version,
		},
	})
}

func (s *Server) handleToolsList(w io.Writer, req *jsonRPCRequest) {
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
		tools = append(tools, tool)
	}
	sendResponse(w, req.ID, map[string]any{
		"tools": tools,
	})
}

func (s *Server) handleToolsCall(ctx context.Context, w io.Writer, req *jsonRPCRequest) {
	var params struct {
		Name      string          `json:"name"`
		Arguments json.RawMessage `json:"arguments"`
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

	result, err := tool.Handler(ctx, params.Arguments)
	if err != nil {
		sendToolError(w, req.ID, err.Error())
		return
	}

	data, err := json.Marshal(result)
	if err != nil {
		sendToolError(w, req.ID, "Failed to marshal tool result: "+err.Error())
		return
	}
	sendToolResponseRaw(w, req.ID, data)
}

func sendResponse(w io.Writer, id any, result any) {
	writeFrame(w, jsonRPCResponse{JSONRPC: "2.0", ID: id, Result: result})
}

func sendToolResponseRaw(w io.Writer, id any, raw json.RawMessage) {
	envelope := fmt.Sprintf(`{"content":[{"type":"text","text":%s}],"isError":false}`, raw)
	writeFrame(w, jsonRPCResponse{JSONRPC: "2.0", ID: id, Result: json.RawMessage(envelope)})
}

func sendToolError(w io.Writer, id any, text string) {
	sendResponse(w, id, map[string]any{
		"content": []map[string]any{
			{"type": "text", "text": text},
		},
		"isError": true,
	})
}

func sendError(w io.Writer, id any, code int, message string) {
	writeFrame(w, jsonRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error: map[string]any{
			"code":    code,
			"message": message,
		},
	})
}
