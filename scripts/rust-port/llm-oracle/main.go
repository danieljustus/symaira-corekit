package main

import (
	"context"
	"encoding/json"
	"errors"
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
	RateLimit                errorResult         `json:"rate_limit"`
	StructuredAuth           errorResult         `json:"structured_auth"`
	StructuredAuthCasefold   errorResult         `json:"structured_auth_casefold"`
	NativeGenerate           struct {
		Request request                   `json:"request"`
		Chunks  []llmkit.GenerateResponse `json:"chunks"`
	} `json:"native_generate"`
	NativeGenerateLargeChunkBytes int `json:"native_generate_large_chunk_response_bytes"`
	NativeChat                    struct {
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
	got, client, closeServer, err = capture("ollama", string(append(largeChunk, '\n')), http.StatusOK)
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
	if err := json.NewEncoder(os.Stdout).Encode(out); err != nil {
		panic(err)
	}
}
