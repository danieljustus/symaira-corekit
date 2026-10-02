package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync/atomic"
	"time"

	"github.com/danieljustus/symaira-corekit/llmkit"
)

type request struct {
	Path            string         `json:"path"`
	Query           string         `json:"query,omitempty"`
	Auth            string         `json:"auth_header"`
	ProviderVersion string         `json:"provider_version,omitempty"`
	Body            map[string]any `json:"body"`
}

type errorResult struct {
	Code       string `json:"code"`
	Status     int    `json:"status"`
	Body       string `json:"body"`
	RetryAfter string `json:"retry_after"`
	Retryable  bool   `json:"retryable"`
	ExitCode   int    `json:"exit_code"`
}

type streamErrorResult struct {
	Code  string `json:"code"`
	Error string `json:"error"`
}

type bodyLimitObservation struct {
	ID           string       `json:"id"`
	BodyPrefix   string       `json:"body_prefix"`
	PaddingBytes int          `json:"padding_bytes"`
	Status       int          `json:"status"`
	Truncated    bool         `json:"truncated"`
	Content      string       `json:"content"`
	Error        *errorResult `json:"error"`
}

func observeBodyLimits() []bodyLimitObservation {
	cases := []bodyLimitObservation{
		{ID: "success-body-over-cap", Status: http.StatusOK, PaddingBytes: 16 << 20,
			BodyPrefix: `{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}`},
		{ID: "error-body-over-cap", Status: http.StatusBadRequest, PaddingBytes: 8 << 10,
			BodyPrefix: `{"error":{"message":"context length exceeded","type":"context_length_exceeded"}}`},
		{ID: "error-body-truncated", Status: http.StatusUnauthorized, Truncated: true,
			BodyPrefix: `{"error":{"message":"authentication failed","type":"authentication_error"}}`},
		{ID: "success-body-truncated", Status: http.StatusOK, Truncated: true,
			BodyPrefix: `{"choices":[{"message":{"content":"ok"},"finish_reason":"stop"}]}`},
	}
	for i := range cases {
		c := &cases[i]
		body := c.BodyPrefix + strings.Repeat(" ", c.PaddingBytes)
		var lengths []int
		if c.Truncated {
			lengths = []int{len(body) + 16}
		}
		_, client, closeServer, err := captureWithSuffix("openai", body, c.Status, "", lengths...)
		if err != nil {
			panic(err)
		}
		choice, err := client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
		closeServer()
		if err == nil {
			c.Content = choice.Content
		} else {
			var classified *llmkit.Error
			if !errors.As(err, &classified) {
				panic(err)
			}
			c.Error = &errorResult{Code: string(classified.Code), Status: classified.StatusCode,
				Body: classified.Body, RetryAfter: classified.RetryAfter,
				Retryable: classified.Retryable(), ExitCode: int(classified.ExitCode())}
		}
	}
	return cases
}

type cancellationResult struct {
	Operation       string `json:"operation"`
	ErrorCode       string `json:"error_code"`
	RequestObserved bool   `json:"request_observed"`
}

type injectedHTTPClientResult struct {
	RegularPath          string `json:"regular_path"`
	RegularContent       string `json:"regular_content"`
	StreamPath           string `json:"stream_path"`
	StreamDelta          string `json:"stream_delta"`
	StreamFinished       string `json:"stream_finished"`
	CancellablePath      string `json:"cancellable_path"`
	CancellationObserved bool   `json:"cancellation_observed"`
	CancellationError    string `json:"cancellation_error"`
}

type injectedHTTPTransport struct {
	started         chan struct{}
	canceled        chan struct{}
	regularPath     string
	streamPath      string
	cancellablePath string
	regularCalls    atomic.Int32
}

func (transport *injectedHTTPTransport) RoundTrip(request *http.Request) (*http.Response, error) {
	if request.URL.Path == "/v1/chat/completions" {
		call := transport.regularCalls.Add(1)
		if call == 1 {
			transport.regularPath = request.URL.Path
			return &http.Response{
				StatusCode: http.StatusOK,
				Header:     http.Header{"Content-Type": []string{"application/json"}},
				Body:       io.NopCloser(strings.NewReader(`{"choices":[{"message":{"content":"injected"}}]}`)),
				Request:    request,
			}, nil
		}
		transport.streamPath = request.URL.Path
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"text/event-stream"}},
			Body: io.NopCloser(strings.NewReader(
				"data: {\"choices\":[{\"delta\":{\"content\":\"first\"}}]}\n\n" +
					"data: {\"choices\":[{\"delta\":{\"content\":\" second\"},\"finish_reason\":\"stop\"}]}\n\n" +
					"data: [DONE]\n\n",
			)),
			Request: request,
		}, nil
	}
	if request.URL.Path == "/v1/embeddings" {
		transport.cancellablePath = request.URL.Path
		select {
		case transport.started <- struct{}{}:
		default:
		}
		<-request.Context().Done()
		select {
		case transport.canceled <- struct{}{}:
		default:
		}
		return nil, request.Context().Err()
	}
	return nil, fmt.Errorf("unexpected injected transport path %s", request.URL.Path)
}

func recordInjectedHTTPClient() injectedHTTPClientResult {
	transport := &injectedHTTPTransport{started: make(chan struct{}, 1), canceled: make(chan struct{}, 1)}
	descriptor, ok := llmkit.Lookup("openai")
	if !ok {
		panic("openai provider not found")
	}
	client, err := llmkit.NewClient(
		descriptor,
		"",
		llmkit.WithBaseURL("http://127.0.0.1:1/v1"),
		llmkit.WithAPIKey("dummy-key"),
		llmkit.WithHTTPClient(&http.Client{Transport: transport}),
	)
	if err != nil {
		panic(err)
	}
	choice, err := client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	if err != nil {
		panic("custom HTTP client regular request failed: " + err.Error())
	}
	var streamDelta, streamFinished string
	err = client.StreamChat(
		context.Background(),
		"gpt-5",
		[]llmkit.Message{{Role: "user", Content: "question"}},
		nil,
		func(delta string) error {
			streamDelta += delta
			return nil
		},
		llmkit.WithStreamFinished(func(reason string) { streamFinished = reason }),
	)
	if err != nil {
		panic("custom HTTP client stream request failed: " + err.Error())
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		_, err := client.Embed(ctx, "", []string{"input"})
		done <- err
	}()
	select {
	case <-transport.started:
	case <-time.After(2 * time.Second):
		cancel()
		panic("custom HTTP client cancellable request did not start")
	}
	cancel()
	select {
	case err = <-done:
	case <-time.After(2 * time.Second):
		panic("custom HTTP client cancellable request did not return")
	}
	providerErr := llmkit.AsError(err)
	if providerErr == nil || providerErr.Code != llmkit.ErrCodeTransport {
		panic(fmt.Sprintf("custom HTTP client cancellation returned unexpected error: %v", err))
	}
	cancellationObserved := false
	select {
	case <-transport.canceled:
		cancellationObserved = true
	case <-time.After(2 * time.Second):
		panic("custom HTTP transport did not observe cancellation")
	}
	if transport.regularCalls.Load() != 2 {
		panic("custom HTTP transport did not receive both chat requests")
	}
	return injectedHTTPClientResult{
		RegularPath:          transport.regularPath,
		RegularContent:       choice.Content,
		StreamPath:           transport.streamPath,
		StreamDelta:          streamDelta,
		StreamFinished:       streamFinished,
		CancellablePath:      transport.cancellablePath,
		CancellationObserved: cancellationObserved,
		CancellationError:    string(providerErr.Code),
	}
}

type openAISuccessToolCall struct {
	ID           string `json:"id"`
	Name         string `json:"name"`
	ArgumentsRaw string `json:"arguments_raw"`
}

type openAISuccessObservation struct {
	ID           string                  `json:"id"`
	Body         string                  `json:"body"`
	Kind         string                  `json:"kind"`
	Content      string                  `json:"content,omitempty"`
	FinishReason string                  `json:"finish_reason,omitempty"`
	ToolCalls    []openAISuccessToolCall `json:"tool_calls,omitempty"`
	ErrorCode    string                  `json:"error_code,omitempty"`
}

type streamCase struct {
	Kind           string             `json:"kind"`
	Request        request            `json:"request"`
	Response       string             `json:"response,omitempty"`
	ResponseBytes  int                `json:"response_bytes"`
	ResponseSHA256 string             `json:"response_sha256"`
	Deltas         []string           `json:"deltas"`
	Events         []string           `json:"events"`
	Finish         string             `json:"finish"`
	Finished       bool               `json:"finished"`
	Error          *streamErrorResult `json:"error"`
}

type observation struct {
	Providers                []llmkit.Descriptor `json:"providers"`
	OpenAI                   request             `json:"openai_chat"`
	OpenAIQuery              request             `json:"openai_query_chat"`
	OpenAIDotPath            request             `json:"openai_dot_path_chat"`
	LoopbackQueryBaseAllowed bool                `json:"loopback_query_base_allowed"`
	EmptyAPIKeyResolves      bool                `json:"empty_api_key_resolves"`
	DialectOverrideAllowed   bool                `json:"dialect_override_allowed"`
	ZeroTimeoutAllowed       bool                `json:"zero_timeout_allowed"`
	Anthropic                request             `json:"anthropic_chat"`
	AnthropicMixedContent    string              `json:"anthropic_mixed_content"`
	OpenAIStream             streamCase          `json:"openai_stream"`
	AnthropicStream          streamCase          `json:"anthropic_stream"`
	OpenAIStreamErrors       struct {
		NoData         streamCase `json:"no_data"`
		BadChunk       streamCase `json:"bad_chunk"`
		OversizedFirst streamCase `json:"oversized_first"`
		OversizedAfter streamCase `json:"oversized_after"`
	} `json:"openai_stream_errors"`
	RateLimit              errorResult `json:"rate_limit"`
	StructuredAuth         errorResult `json:"structured_auth"`
	StructuredAuthCasefold errorResult `json:"structured_auth_casefold"`
	MalformedEnvelope      errorResult `json:"malformed_error_envelope"`
	MalformedChoice        errorResult `json:"malformed_error_choice"`
	MalformedChoiceAlias   errorResult `json:"malformed_error_choice_alias_collision"`
	MalformedNestedAlias   errorResult `json:"malformed_error_nested_alias_collision"`
	NullChoiceContent      string      `json:"null_choice_content"`
	InvalidUTF8ErrorBody   string      `json:"invalid_utf8_error_body"`
	NativeGenerate         struct {
		Request request                   `json:"request"`
		Chunks  []llmkit.GenerateResponse `json:"chunks"`
	} `json:"native_generate"`
	NativeGenerateLargeChunkBytes int `json:"native_generate_large_chunk_response_bytes"`
	NativeGenerateScannerErrors   struct {
		BeforeData streamErrorResult `json:"before_data"`
		AfterData  streamErrorResult `json:"after_data"`
	} `json:"native_generate_scanner_errors"`
	NativeGenerateWhitespaceLine streamErrorResult `json:"native_generate_whitespace_line"`
	NativeGenerateDecodeErrors   struct {
		Truncated streamErrorResult `json:"truncated"`
		BadKey    streamErrorResult `json:"bad_key"`
		Trailing  streamErrorResult `json:"trailing"`
	} `json:"native_generate_decode_errors"`
	NativeChat struct {
		Request request                     `json:"request"`
		Chunks  []llmkit.ChatStreamResponse `json:"chunks"`
	} `json:"native_chat"`
	NativeEmbed struct {
		Request    request     `json:"request"`
		Embeddings [][]float32 `json:"embeddings"`
	} `json:"native_embed"`
	OpenAIEmbed struct {
		Request request     `json:"request"`
		Vectors [][]float32 `json:"vectors"`
	} `json:"openai_embed"`
	CasefoldEmbedding struct {
		DataThenAlias      []float32 `json:"data_then_alias"`
		AliasThenData      []float32 `json:"alias_then_data"`
		EmbeddingThenAlias []float32 `json:"embedding_then_alias"`
		AliasThenEmbedding []float32 `json:"alias_then_embedding"`
	} `json:"casefold_embedding"`
	NativeModels struct {
		Request request                  `json:"request"`
		Models  []llmkit.OllamaModelInfo `json:"models"`
	} `json:"native_models"`
	PingOllama struct {
		Request  request `json:"request"`
		Response string  `json:"response"`
	} `json:"ping_ollama"`
	NativeModelsCasefold        []llmkit.OllamaModelInfo   `json:"native_models_casefold_alias_order"`
	CasefoldDiscoveryModels     []llmkit.ModelInfo         `json:"casefold_discovery_models"`
	GenericOllamaCasefoldModels []llmkit.ModelInfo         `json:"generic_ollama_casefold_models"`
	CancellableCalls            []cancellationResult       `json:"cancellable_calls"`
	InjectedHTTPClient          injectedHTTPClientResult   `json:"injected_http_client"`
	OpenAISuccessResponses      []openAISuccessObservation `json:"openai_success_responses"`
	BodyLimits                  []bodyLimitObservation     `json:"body_limits"`
}

func canceledCall(operation string, requests *atomic.Int32, call func(context.Context) error) cancellationResult {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	before := requests.Load()
	err := call(ctx)
	providerErr := llmkit.AsError(err)
	if providerErr == nil || providerErr.Code != llmkit.ErrCodeTransport {
		panic(operation + ": expected transport error for canceled context")
	}
	return cancellationResult{
		Operation: operation, ErrorCode: string(providerErr.Code), RequestObserved: requests.Load() != before,
	}
}

func recordCanceledCalls(baseURL string, requests *atomic.Int32) []cancellationResult {
	openAI, _ := llmkit.Lookup("openai")
	openAIClient, err := llmkit.NewClient(openAI, "", llmkit.WithBaseURL(baseURL+"/v1"), llmkit.WithAPIKey("dummy-key"))
	if err != nil {
		panic(err)
	}
	openRouter, _ := llmkit.Lookup("openrouter")
	openRouterClient, err := llmkit.NewClient(openRouter, "", llmkit.WithBaseURL(baseURL+"/api/v1"), llmkit.WithAPIKey("dummy-key"))
	if err != nil {
		panic(err)
	}
	ollama, _ := llmkit.Lookup("ollama")
	ollamaClient, err := llmkit.NewClient(ollama, "", llmkit.WithBaseURL(baseURL))
	if err != nil {
		panic(err)
	}
	message := []llmkit.Message{{Role: "user", Content: "question"}}
	return []cancellationResult{
		canceledCall("embed", requests, func(ctx context.Context) error {
			_, err := openAIClient.Embed(ctx, "", []string{"input"})
			return err
		}),
		canceledCall("list_models", requests, func(ctx context.Context) error {
			_, err := openRouterClient.ListModels(ctx)
			return err
		}),
		canceledCall("embed_native", requests, func(ctx context.Context) error {
			_, err := ollamaClient.EmbedNative(ctx, "", []string{"input"}, 2)
			return err
		}),
		canceledCall("list_ollama_models", requests, func(ctx context.Context) error {
			_, err := ollamaClient.ListOllamaModels(ctx)
			return err
		}),
		canceledCall("generate", requests, func(ctx context.Context) error {
			return ollamaClient.Generate(ctx, "", "prompt", func(llmkit.GenerateResponse) error { return nil })
		}),
		canceledCall("chat_stream", requests, func(ctx context.Context) error {
			return ollamaClient.ChatStream(ctx, "", message, func(llmkit.ChatStreamResponse) error { return nil })
		}),
		canceledCall("ping", requests, func(ctx context.Context) error {
			return ollamaClient.Ping(ctx)
		}),
	}
}

var openAISuccessResponseBodies = []struct {
	id   string
	body string
}{
	{"missing_fields", `{}`},
	{"null_choices", `{"choices":null}`},
	{"null_choice", `{"choices":[null]}`},
	{"null_message", `{"choices":[{"message":null,"finish_reason":"stop"}]}`},
	{"null_scalars_preserve_previous", `{"choices":[{"message":{"content":"kept"},"MESSAGE":{"CONTENT":null},"finish_reason":"stop","FINISH_REASON":null}]}`},
	{"null_tool_calls_clears_array", `{"choices":[{"message":{"tool_calls":[{"id":"discard","function":{"name":"discard","arguments":"{}"}}]},"MESSAGE":{"tool_calls":null}}]}`},
	{"null_tool_calls_reset_before_same_message_array", `{"choices":[{"message":{"tool_calls":[{"id":"old","function":{"name":"old","arguments":"old"}}]},"MESSAGE":{"tool_calls":null,"TOOL_CALLS":[{"id":"new"}]}}]}`},
	{"null_tool_calls_reset_before_repeated_choice_array", `{"choices":[{"message":{"tool_calls":[{"id":"old","function":{"name":"old","arguments":"old"}}]}}],"CHOICES":[{"message":{"tool_calls":null,"TOOL_CALLS":[{"id":"new"}]}}]}`},
	{"null_function_preserves_previous", `{"choices":[{"message":{"tool_calls":[{"id":"call-1","function":{"name":"lookup","arguments":"{\"q\":1}"}}]},"MESSAGE":{"tool_calls":[{"id":"call-1","FUNCTION":null}]}}]}`},
	{"null_function_value_preserves_previous", `{"choices":[{"message":{"tool_calls":[{"id":"call-null-fn","function":{"name":"keep","arguments":"{}"},"FUNCTION":null}]} }]}`},
	{"null_tool_call_zero_value", `{"choices":[{"message":{"tool_calls":[null]}}]}`},
	{"casefold_fields_and_unknown_ignored", `{"CHOICES":[{"MESSAGE":{"CONTENT":"folded","TOOL_CALLS":[{"ID":"call-fold","FUNCTION":{"NAME":"search","ARGUMENTS":"{\"term\":\"rust\"}","extra":true}}]},"FINISH_REASON":"tool_calls","unknown":{"nested":[1,2]}}]}`},
	{"unicode_fold_aliases", `{"choiceſ":[{"message":{"content":"unicode folded","finish_reaſon":"stop","tool_calls":[{"function":{"name":"lookup","argumentſ":"{}"}}]}}]}`},
	{"duplicate_scalar_last_wins", `{"choices":[{"finish_reason":"first","FINISH_REASON":"last","message":{"content":"first","CONTENT":"last"}}]}`},
	{"repeated_nested_objects_merge", `{"choices":[{"message":{"content":"merged","tool_calls":[{"id":"call-merge","function":{"name":"fn-merge","arguments":"{\"ok\":true}"}}]},"MESSAGE":{"tool_calls":[{"FUNCTION":{"name":"fn-alias","arguments":"{\"alias\":true}"}}]}}]}`},
	{"repeated_function_objects_merge", `{"choices":[{"message":{"tool_calls":[{"id":"call-fn-merge","function":{"name":"fn-kept","arguments":"{\"old\":true}"},"FUNCTION":{"arguments":"{\"new\":true}"}}]}}]}`},
	{"duplicate_arrays_replace", `{"choices":[{"message":{"tool_calls":[{"id":"old","function":{"name":"old","arguments":"{}"}}],"TOOL_CALLS":[{"id":"new","function":{"name":"new","arguments":"{\"new\":true}"}}]}}]}`},
	{"tool_call_backing_slots_reappear_after_shrink", `{"choices":[{"message":{"tool_calls":[{"id":"first","function":{"name":"kept-first","arguments":"{\"slot\":1}"}},{"id":"second","function":{"name":"kept-second","arguments":"{\"slot\":2}"}}]}}],"CHOICES":[{"MESSAGE":{"TOOL_CALLS":[{"id":"middle","function":{"name":"middle","arguments":"{\"middle\":true}"}}]}}],"choices":[{"message":{"tool_calls":[{"id":"final-first","function":null},{"id":"final-second","function":null}]}}]}`},
	{"choice_backing_slots_reappear_after_shrink", `{"choices":[{"message":{"content":"slot-zero"},"finish_reason":"first"},{"message":{"content":"slot-one"},"finish_reason":"second"}],"CHOICES":[{"message":{"content":"middle"},"finish_reason":"middle"}],"choices":[{"message":null,"finish_reason":null},{"message":null,"finish_reason":null}]}`},
	{"casefold_alias_order_last_wins", `{"choices":[{"message":{"content":"lower"},"MESSAGE":{"CONTENT":"upper"}}]}`},
	{"null_content_zero_value", `{"choices":[{"message":{"content":null},"finish_reason":null}]}`},
	{"top_level_error_ignored_on_success", `{"error":{"message":"ignored","type":"server_error"},"choices":[{"message":{"content":"choice wins"}}]}`},
	{"malformed_top_level_error_type", `{"error":{"message":5},"choices":[{"message":{"content":"unreachable"}}]}`},
	{"error_code_numeric_overflow_rejected", `{"error":{"code":1e400},"choices":[{"message":{"content":"unreachable"}}]}`},
	{"error_code_nested_numeric_overflow_rejected", `{"error":{"code":[1e400]},"choices":[{"message":{"content":"unreachable"}}]}`},
	{"unknown_numeric_overflow_ignored", `{"unknown":1e400,"choices":[{"message":{"content":"unknown ignored"}}]}`},
	{"wrong_content_type", `{"choices":[{"message":{"content":42}}]}`},
	{"wrong_tool_calls_type", `{"choices":[{"message":{"tool_calls":{}}}]}`},
	{"wrong_tool_type_type", `{"choices":[{"message":{"tool_calls":[{"type":42}]}}]}`},
}

func observeOpenAISuccessResponses() []openAISuccessObservation {
	observations := make([]openAISuccessObservation, 0, len(openAISuccessResponseBodies))
	for _, test := range openAISuccessResponseBodies {
		observation := openAISuccessObservation{ID: test.id, Body: test.body}
		_, client, closeServer, err := capture("openai", test.body, http.StatusOK)
		if err != nil {
			panic(err)
		}
		choice, err := client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
		closeServer()
		if err != nil {
			var providerErr *llmkit.Error
			if !errors.As(err, &providerErr) {
				panic("expected llmkit error for OpenAI success-response corpus")
			}
			observation.Kind = "error"
			observation.ErrorCode = string(providerErr.Code)
		} else {
			observation.Kind = "success"
			observation.Content = choice.Content
			observation.FinishReason = choice.FinishReason
			for _, call := range choice.ToolCalls {
				observation.ToolCalls = append(observation.ToolCalls, openAISuccessToolCall{
					ID: call.ID, Name: call.Name, ArgumentsRaw: string(call.Arguments),
				})
			}
		}
		observations = append(observations, observation)
	}
	return observations
}

func capture(provider, response string, status int) (*request, *llmkit.Client, func(), error) {
	return captureWithSuffix(provider, response, status, "")
}

func captureWithSuffix(provider, response string, status int, suffix string, contentLength ...int) (*request, *llmkit.Client, func(), error) {
	got := &request{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.Path = r.URL.Path
		got.Query = r.URL.RawQuery
		if strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") {
			got.Auth = "bearer"
		}
		if r.Header.Get("x-api-key") != "" {
			got.Auth = "x-api-key"
		}
		got.ProviderVersion = r.Header.Get("anthropic-version")
		_ = json.NewDecoder(r.Body).Decode(&got.Body)
		w.Header().Set("Content-Type", "application/json")
		if len(contentLength) != 0 {
			w.Header().Set("Content-Length", fmt.Sprint(contentLength[0]))
		}
		if status != 0 {
			w.Header().Set("Retry-After", "17")
		}
		w.WriteHeader(status)
		_, _ = w.Write([]byte(response))
	}))
	desc, ok := llmkit.Lookup(provider)
	if !ok {
		server.Close()
		return got, nil, func() {}, errors.New("provider not found")
	}
	baseURL := server.URL
	if provider == "openai" {
		baseURL += "/v1"
	}
	baseURL += suffix
	client, err := llmkit.NewClient(desc, "", llmkit.WithBaseURL(baseURL), llmkit.WithAPIKey("dummy-key"))
	if err != nil {
		server.Close()
		return got, nil, func() {}, err
	}
	return got, client, server.Close, nil
}

// runStream records one SSE streaming observation: the wire request, the raw
// response bytes, every callback delta, the finish reason, and any llmkit
// error. Response bodies over four KiB are recorded by kind and SHA-256 only
// so oversized scanner fixtures stay out of the committed JSON.
func runStream(kind, provider, model, response string, opts *llmkit.ChatOptions) streamCase {
	sum := sha256.Sum256([]byte(response))
	result := streamCase{
		Kind:           kind,
		Response:       response,
		ResponseBytes:  len(response),
		ResponseSHA256: fmt.Sprintf("%x", sum),
		Deltas:         []string{},
		Events:         []string{},
	}
	if result.ResponseBytes > 4096 {
		result.Response = ""
	}
	got := &request{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.Path = r.URL.Path
		got.Query = r.URL.RawQuery
		if strings.HasPrefix(r.Header.Get("Authorization"), "Bearer ") {
			got.Auth = "bearer"
		}
		if r.Header.Get("x-api-key") != "" {
			got.Auth = "x-api-key"
		}
		got.ProviderVersion = r.Header.Get("anthropic-version")
		_ = json.NewDecoder(r.Body).Decode(&got.Body)
		w.Header().Set("Content-Type", "text/event-stream")
		_, _ = w.Write([]byte(response))
	}))
	desc, ok := llmkit.Lookup(provider)
	if !ok {
		server.Close()
		panic(kind + ": provider not found")
	}
	baseURL := server.URL
	if provider == "openai" {
		baseURL += "/v1"
	}
	client, err := llmkit.NewClient(desc, "", llmkit.WithBaseURL(baseURL), llmkit.WithAPIKey("dummy-key"))
	if err != nil {
		server.Close()
		panic(err)
	}
	callErr := client.StreamChat(context.Background(), model,
		[]llmkit.Message{{Role: "user", Content: "question"}}, opts,
		func(delta string) error {
			result.Deltas = append(result.Deltas, delta)
			result.Events = append(result.Events, "delta:"+delta)
			return nil
		},
		llmkit.WithStreamFinished(func(reason string) {
			result.Finish = reason
			result.Finished = true
			result.Events = append(result.Events, "finish:"+reason)
		}))
	server.Close()
	result.Request = *got
	if callErr != nil {
		var providerErr *llmkit.Error
		if !errors.As(callErr, &providerErr) {
			panic(kind + ": expected llmkit stream error: " + callErr.Error())
		}
		result.Error = &streamErrorResult{Code: string(providerErr.Code), Error: callErr.Error()}
	}
	return result
}

func main() {
	providers, err := llmkit.Providers()
	if err != nil {
		panic(err)
	}
	var out observation
	out.Providers = providers
	out.OpenAISuccessResponses = observeOpenAISuccessResponses()
	out.BodyLimits = observeBodyLimits()
	out.InjectedHTTPClient = recordInjectedHTTPClient()
	var canceledRequests atomic.Int32
	cancelServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		canceledRequests.Add(1)
		_, _ = w.Write([]byte(`{}`))
	}))
	out.CancellableCalls = recordCanceledCalls(cancelServer.URL, &canceledRequests)
	cancelServer.Close()
	if canceledRequests.Load() != 0 {
		panic("canceled calls unexpectedly reached HTTP server")
	}
	openAI, ok := llmkit.Lookup("openai")
	if !ok {
		panic("openai provider not found")
	}
	_, err = llmkit.NewClient(openAI, "", llmkit.WithBaseURL("http://localhost:11434?api-version=2026-01-01"), llmkit.WithAPIKey("dummy-key"))
	out.LoopbackQueryBaseAllowed = err == nil
	_, err = llmkit.NewClient(openAI, "env://", llmkit.WithAPIKey(""))
	out.EmptyAPIKeyResolves = err != nil
	_, err = llmkit.NewClient(openAI, "", llmkit.WithAPIKey("dummy-key"), llmkit.WithDialect(llmkit.DialectAnthropic))
	out.DialectOverrideAllowed = err == nil
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"choices":[{"message":{"content":"answer"}}]}`))
	}))
	zeroTimeoutClient, err := llmkit.NewClient(openAI, "", llmkit.WithBaseURL(server.URL+"/v1"), llmkit.WithAPIKey("dummy-key"), llmkit.WithTimeout(0))
	if err == nil {
		_, err = zeroTimeoutClient.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	}
	out.ZeroTimeoutAllowed = err == nil
	server.Close()
	got, client, closeServer, err := capture("openai", `{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, &llmkit.ChatOptions{System: "system prompt", MaxTokens: 32})
	if err != nil {
		panic(err)
	}
	closeServer()
	out.OpenAI = *got
	got, client, closeServer, err = captureWithSuffix("openai", `{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}`, http.StatusOK, "?api-version=2026-01-01")
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	if err != nil {
		panic(err)
	}
	closeServer()
	out.OpenAIQuery = *got
	got, client, closeServer, err = captureWithSuffix("openai", `{"choices":[{"message":{"content":"answer"},"finish_reason":"stop"}]}`, http.StatusOK, "/../api/./?api-version=2026-01-01")
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	if err != nil {
		panic(err)
	}
	closeServer()
	out.OpenAIDotPath = *got
	got, client, closeServer, err = capture("anthropic", `{"content":[{"type":"text","text":"answer"}],"stop_reason":"end_turn"}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "claude", []llmkit.Message{{Role: "system", Content: "rules"}, {Role: "user", Content: "question"}}, nil)
	if err != nil {
		panic(err)
	}
	closeServer()
	out.Anthropic = *got
	_, client, closeServer, err = capture("anthropic", `{"content":[{"type":"text","text":"first"},{"type":"tool_use","text":"second"}],"stop_reason":"end_turn"}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	choice, err := client.Chat(context.Background(), "claude", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if err != nil {
		panic(err)
	}
	out.AnthropicMixedContent = choice.Content
	_, client, closeServer, err = capture("openai", `{"error":"busy"}`, http.StatusTooManyRequests)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	var providerErr *llmkit.Error
	if !errors.As(err, &providerErr) {
		panic("expected llmkit error")
	}
	out.RateLimit = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"error":{"message":"authentication failed","type":"authentication_error"}}`, http.StatusUnauthorized)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected structured llmkit error")
	}
	out.StructuredAuth = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"ERROR":{"MESSAGE":"authentication failed","TYPE":"authentication_error"}}`, http.StatusUnauthorized)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected casefold structured llmkit error")
	}
	out.StructuredAuthCasefold = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"error":{"message":"authentication failed","type":"authentication_error"},"choices":"malformed"}`, http.StatusUnauthorized)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected malformed-envelope provider error")
	}
	out.MalformedEnvelope = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"error":{"message":"rate limit exceeded","type":"rate_limit_error"},"choices":[{"message":"malformed"}]}`, http.StatusTooManyRequests)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected malformed-choice provider error")
	}
	out.MalformedChoice = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"choices":[],"error":{"message":"authentication failed","type":"authentication_error"},"CHOICES":"malformed"}`, http.StatusUnauthorized)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected malformed aliased-choice provider error")
	}
	out.MalformedChoiceAlias = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"error":{"message":"authentication failed","type":"authentication_error"},"choices":[{"message":{"content":"ok","CONTENT":5}}]}`, http.StatusUnauthorized)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected malformed nested-choice provider error")
	}
	out.MalformedNestedAlias = errorResult{Code: string(providerErr.Code), Status: providerErr.StatusCode, Body: providerErr.Body, RetryAfter: providerErr.RetryAfter, Retryable: providerErr.Retryable(), ExitCode: int(providerErr.ExitCode())}
	_, client, closeServer, err = capture("openai", `{"choices":[null]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	choice, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if err != nil {
		panic(err)
	}
	out.NullChoiceContent = choice.Content
	rawErrorBody := append(bytes.Repeat([]byte{0xff}, 171), bytes.Repeat([]byte("x"), 500)...)
	_, client, closeServer, err = capture("openai", string(rawErrorBody), http.StatusBadRequest)
	if err != nil {
		panic(err)
	}
	_, err = client.Chat(context.Background(), "gpt-5", []llmkit.Message{{Role: "user", Content: "question"}}, nil)
	closeServer()
	if !errors.As(err, &providerErr) {
		panic("expected invalid UTF-8 provider error")
	}
	out.InvalidUTF8ErrorBody = providerErr.Body
	got, client, closeServer, err = capture("ollama", "{\"model\":\"llama3.1\",\"response\":\"piece\",\"done\":false}\n{\"model\":\"llama3.1\",\"response\":\"\",\"done\":true}\n", http.StatusOK)
	if err != nil {
		panic(err)
	}
	err = client.Generate(context.Background(), "", "prompt", func(value llmkit.GenerateResponse) error {
		out.NativeGenerate.Chunks = append(out.NativeGenerate.Chunks, value)
		return nil
	}, llmkit.WithGenerateSystem("system"), llmkit.WithGenerateFormatValue("json"), llmkit.WithGenerateTemperature(0.25), llmkit.WithGenerateImages([]string{"aW1hZ2U="}))
	if err != nil {
		panic(err)
	}
	closeServer()
	out.NativeGenerate.Request = *got
	largeChunk, err := json.Marshal(llmkit.GenerateResponse{
		Model: "llama3.1", Response: strings.Repeat("x", 2*1024*1024), Done: true,
	})
	if err != nil {
		panic(err)
	}
	_, client, closeServer, err = capture("ollama", string(append(largeChunk, '\n')), http.StatusOK)
	if err != nil {
		panic(err)
	}
	err = client.Generate(context.Background(), "", "prompt", func(value llmkit.GenerateResponse) error {
		out.NativeGenerateLargeChunkBytes = len(value.Response)
		return nil
	})
	if err != nil {
		panic(err)
	}
	closeServer()
	largeLine, err := json.Marshal(llmkit.GenerateResponse{
		Model: "llama3.1", Response: strings.Repeat("x", 4*1024*1024), Done: true,
	})
	if err != nil {
		panic(err)
	}
	streamError := func(response string) streamErrorResult {
		_, client, closeServer, err := capture("ollama", response, http.StatusOK)
		if err != nil {
			panic(err)
		}
		err = client.Generate(context.Background(), "", "prompt", func(llmkit.GenerateResponse) error { return nil })
		closeServer()
		var providerErr *llmkit.Error
		if !errors.As(err, &providerErr) {
			panic("expected scanner failure as llmkit error")
		}
		return streamErrorResult{Code: string(providerErr.Code), Error: err.Error()}
	}
	out.NativeGenerateScannerErrors.BeforeData = streamError(string(append(largeLine, '\n')))
	out.NativeGenerateScannerErrors.AfterData = streamError("{\"model\":\"llama3.1\",\"response\":\"first\",\"done\":false}\n" + string(append(largeLine, '\n')))
	out.NativeGenerateWhitespaceLine = streamError(" \n{\"model\":\"llama3.1\",\"response\":\"second\",\"done\":true}\n")
	out.NativeGenerateDecodeErrors.Truncated = streamError("{\"model\":\n")
	out.NativeGenerateDecodeErrors.BadKey = streamError("{bad}\n")
	out.NativeGenerateDecodeErrors.Trailing = streamError("{\"model\":\"llama3.1\",\"response\":5,\"done\":true,\"metadata\":{\"text\":\"} ] { in string\"}}x\n")
	got, client, closeServer, err = capture("ollama", "{\"model\":\"llama3.1\",\"message\":{\"role\":\"assistant\",\"content\":\"piece\"},\"done\":true}\n", http.StatusOK)
	if err != nil {
		panic(err)
	}
	err = client.ChatStreamWithOptions(context.Background(), "", []llmkit.Message{{Role: "user", Content: "question"}}, func(value llmkit.ChatStreamResponse) error {
		out.NativeChat.Chunks = append(out.NativeChat.Chunks, value)
		return nil
	}, llmkit.WithNativeChatTemperature(0.5), llmkit.WithNativeChatFormat("json"))
	if err != nil {
		panic(err)
	}
	closeServer()
	out.NativeChat.Request = *got
	got, client, closeServer, err = capture("ollama", `{"embeddings":[[0.25,0.5]]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	out.NativeEmbed.Embeddings, err = client.EmbedNative(context.Background(), "", []string{"input"}, 2)
	if err != nil {
		panic(err)
	}
	closeServer()
	out.NativeEmbed.Request = *got
	casefoldResponses := []struct {
		response string
	}{
		{`{"data":[{"embedding":[0.1]}],"dAtA":[{"embedding":[0.2]}]}`},
		{`{"dAtA":[{"embedding":[0.3]}],"data":[{"embedding":[0.4]}]}`},
		{`{"data":[{"embedding":[0.5],"eMbEdDiNg":[0.6]}]}`},
		{`{"data":[{"eMbEdDiNg":[0.7],"embedding":[0.8]}]}`},
	}
	var casefoldVectors [][]float32
	for _, test := range casefoldResponses {
		_, client, closeServer, err = capture("openai", test.response, http.StatusOK)
		if err != nil {
			panic(err)
		}
		embeddings, err := client.Embed(context.Background(), "", []string{"input"})
		closeServer()
		if err != nil || len(embeddings) != 1 {
			panic("expected one case-folded embedding")
		}
		casefoldVectors = append(casefoldVectors, embeddings[0].Vector)
	}
	out.CasefoldEmbedding.DataThenAlias = casefoldVectors[0]
	out.CasefoldEmbedding.AliasThenData = casefoldVectors[1]
	out.CasefoldEmbedding.EmbeddingThenAlias = casefoldVectors[2]
	out.CasefoldEmbedding.AliasThenEmbedding = casefoldVectors[3]
	got, client, closeServer, err = capture("openai", `{"data":[{"embedding":[0.25,0.5]}]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	embeddings, err := client.Embed(context.Background(), "", []string{"input"}, llmkit.WithEmbedDimensions(2))
	closeServer()
	if err != nil || len(embeddings) != 1 {
		panic("expected one OpenAI embedding")
	}
	out.OpenAIEmbed.Request = *got
	out.OpenAIEmbed.Vectors = [][]float32{embeddings[0].Vector}
	got, client, closeServer, err = capture("ollama", `{"models":[{"name":"llama3.1","modified_at":"today","size":12}]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	out.NativeModels.Models, err = client.ListOllamaModels(context.Background())
	if err != nil {
		panic(err)
	}
	closeServer()
	out.NativeModels.Request = *got
	_, client, closeServer, err = capture("ollama", `{"models":[{"name":"older-model","modified_at":"yesterday","size":99}],"MODELS":[{"NAME":"current-model","MODIFIED_AT":"today","SIZE":12}]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	out.NativeModelsCasefold, err = client.ListOllamaModels(context.Background())
	if err != nil {
		panic(err)
	}
	closeServer()
	_, client, closeServer, err = captureWithSuffix("openrouter", `{"data":[{"id":"older-model"}],"DaTa":[{"ID":"vendor/current-model"}]}`, http.StatusOK, "/api/v1")
	if err != nil {
		panic(err)
	}
	out.CasefoldDiscoveryModels, err = client.ListModels(context.Background())
	if err != nil {
		panic(err)
	}
	closeServer()
	_, client, closeServer, err = capture("ollama", `{"models":[{"name":"older-model"}],"MODELS":[{"NAME":"current-model"}]}`, http.StatusOK)
	if err != nil {
		panic(err)
	}
	out.GenericOllamaCasefoldModels, err = client.ListModels(context.Background())
	if err != nil {
		panic(err)
	}
	closeServer()
	pingResponse := `{"data":[{"id":"pong"}]}`
	got, client, closeServer, err = capture("ollama", pingResponse, http.StatusOK)
	if err != nil {
		panic(err)
	}
	if err := client.Ping(context.Background()); err != nil {
		panic(err)
	}
	out.PingOllama.Request = *got
	out.PingOllama.Response = pingResponse
	closeServer()

	// SSE streaming parity: record Go StreamChat wire bytes, callback order,
	// finish reasons, and malformed-stream errors for the Rust replay tests.
	temp := 0.5
	chatOpts := &llmkit.ChatOptions{Temperature: &temp, MaxTokens: 64, System: "system prompt"}
	openAIChunks := "data: {\"choices\":[{\"delta\":{\"content\":\"first\"}}]}\n\n" +
		"data: {\"choices\":[{\"delta\":{\"content\":\" second\"},\"finish_reason\":\"stop\"}]}\n\n" +
		"data: [DONE]\n\n"
	out.OpenAIStream = runStream("openai_stream_ok", "openai", "gpt-5", openAIChunks, chatOpts)
	out.AnthropicStream = runStream("anthropic_stream_ok", "anthropic", "claude", "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"first\"}}\n\n"+
		"data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\" second\"}}\n\n"+
		"data: {\"type\":\"message_delta\",\"delta\":{\"stop_reason\":\"end_turn\"},\"usage\":{\"output_tokens\":2}}\n\n", chatOpts)
	out.OpenAIStreamErrors.NoData = runStream("openai_stream_no_data", "openai", "gpt-5", ": keep-alive\n\n", nil)
	out.OpenAIStreamErrors.BadChunk = runStream("openai_stream_bad_chunk", "openai", "gpt-5", "data: {bad}\n\n", nil)
	oversizedLine := "data: " + strings.Repeat("x", 1024*1024+1) + "\n"
	out.OpenAIStreamErrors.OversizedFirst = runStream("openai_stream_oversized_first", "openai", "gpt-5", oversizedLine, nil)
	out.OpenAIStreamErrors.OversizedAfter = runStream("openai_stream_oversized_after", "openai", "gpt-5",
		"data: {\"choices\":[{\"delta\":{\"content\":\"first\"}}]}\n\n"+oversizedLine, nil)
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		panic(err)
	}
}
