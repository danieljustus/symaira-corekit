package llmkit

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"
)

func TestNativeOllamaCompatibilitySurface(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/x-ndjson")
		switch r.URL.Path {
		case "/api/embed":
			var body struct {
				Model      string   `json:"model"`
				Input      []string `json:"input"`
				Dimensions int      `json:"dimensions"`
			}
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			if body.Model != "embed-model" || !reflect.DeepEqual(body.Input, []string{"one", "two"}) || body.Dimensions != 3 {
				http.Error(w, fmt.Sprintf("unexpected embed request: %+v", body), http.StatusBadRequest)
				return
			}
			_, _ = fmt.Fprintln(w, `{"embeddings":[[1,2,3],[4,5,6]]}`)
		case "/api/tags":
			_, _ = fmt.Fprintln(w, `{"models":[{"name":"llama3","modified_at":"2026-08-29T10:00:00Z","size":123}]}`)
		case "/api/generate":
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			if body["format"] != "json" || body["temperature"] != 0.25 || !reflect.DeepEqual(body["images"], []any{"aGVsbG8="}) {
				http.Error(w, fmt.Sprintf("unexpected generate request: %#v", body), http.StatusBadRequest)
				return
			}
			_, _ = fmt.Fprintln(w, `{"model":"llama3","response":"ok","done":false}`)
			_, _ = fmt.Fprintln(w, `{"model":"llama3","response":"","done":true}`)
		case "/api/chat":
			var body map[string]any
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			if body["format"] != "json" || body["temperature"] != 0.5 {
				http.Error(w, fmt.Sprintf("unexpected chat request: %#v", body), http.StatusBadRequest)
				return
			}
			_, _ = fmt.Fprintln(w, `{"model":"llama3","message":{"role":"assistant","content":"ok"},"done":true}`)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	desc, ok := Lookup("ollama")
	if !ok {
		t.Fatal("ollama descriptor is missing")
	}
	client, err := NewClient(desc, "", WithBaseURL(server.URL), WithHTTPClient(server.Client()))
	if err != nil {
		t.Fatal(err)
	}

	embeddings, err := client.EmbedNative(context.Background(), "embed-model", []string{"one", "two"}, 3)
	if err != nil || !reflect.DeepEqual(embeddings, [][]float32{{1, 2, 3}, {4, 5, 6}}) {
		t.Fatalf("EmbedNative() = %#v, %v", embeddings, err)
	}

	models, err := client.ListOllamaModels(context.Background())
	if err != nil || len(models) != 1 || models[0].Name != "llama3" || models[0].Size != 123 {
		t.Fatalf("ListOllamaModels() = %#v, %v", models, err)
	}
	if err := client.Ping(context.Background()); err != nil {
		t.Fatalf("Ping() error = %v", err)
	}

	var generated int
	err = client.Generate(context.Background(), "llama3", "prompt", func(response GenerateResponse) error {
		generated++
		return nil
	}, WithGenerateFormatValue("json"), WithGenerateTemperature(0.25), WithGenerateImages([]string{"aGVsbG8="}))
	if err != nil || generated != 2 {
		t.Fatalf("Generate() count = %d, error = %v", generated, err)
	}

	var chats int
	err = client.ChatStreamWithOptions(context.Background(), "llama3", []Message{{Role: "user", Content: "hi"}}, func(response ChatStreamResponse) error {
		chats++
		return nil
	}, WithNativeChatFormat("json"), WithNativeChatTemperature(0.5))
	if err != nil || chats != 1 {
		t.Fatalf("ChatStreamWithOptions() count = %d, error = %v", chats, err)
	}
}

func TestNativeOllamaMethodsRejectOtherProviders(t *testing.T) {
	desc, ok := Lookup("openai")
	if !ok {
		t.Fatal("openai descriptor is missing")
	}
	client, err := NewClient(desc, "", WithAPIKey("test-key"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.EmbedNative(context.Background(), "model", []string{"input"}, 0); err == nil {
		t.Fatal("EmbedNative() unexpectedly accepted a non-Ollama provider")
	}
	if _, err := client.ListOllamaModels(context.Background()); err == nil {
		t.Fatal("ListOllamaModels() unexpectedly accepted a non-Ollama provider")
	}
}
