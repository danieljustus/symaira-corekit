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
	Providers      []llmkit.Descriptor `json:"providers"`
	OpenAI         request             `json:"openai_chat"`
	Anthropic      request             `json:"anthropic_chat"`
	RateLimit      errorResult         `json:"rate_limit"`
	NativeGenerate struct {
		Request request                   `json:"request"`
		Chunks  []llmkit.GenerateResponse `json:"chunks"`
	} `json:"native_generate"`
	NativeChat struct {
		Request request                     `json:"request"`
		Chunks  []llmkit.ChatStreamResponse `json:"chunks"`
	} `json:"native_chat"`
	NativeEmbed struct {
		Request    request     `json:"request"`
		Embeddings [][]float32 `json:"embeddings"`
	} `json:"native_embed"`
	NativeModels struct {
		Request request                  `json:"request"`
		Models  []llmkit.OllamaModelInfo `json:"models"`
	} `json:"native_models"`
}

func capture(provider, response string, status int) (*request, *llmkit.Client, func(), error) {
	got := &request{}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		got.Path = r.URL.Path
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
