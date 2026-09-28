package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"

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
	NativeModelsCasefold        []llmkit.OllamaModelInfo `json:"native_models_casefold_alias_order"`
	CasefoldDiscoveryModels     []llmkit.ModelInfo       `json:"casefold_discovery_models"`
	GenericOllamaCasefoldModels []llmkit.ModelInfo       `json:"generic_ollama_casefold_models"`
}

func capture(provider, response string, status int) (*request, *llmkit.Client, func(), error) {
	return captureWithSuffix(provider, response, status, "")
}

func captureWithSuffix(provider, response string, status int, suffix string) (*request, *llmkit.Client, func(), error) {
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
