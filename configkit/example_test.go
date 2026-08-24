package configkit_test

import (
	"fmt"

	"github.com/danieljustus/symaira-corekit/configkit"
)

// AppConfig is a demonstration configuration type.
type AppConfig struct {
	Server struct {
		Host string `json:"host"`
		Port int    `json:"port"`
	} `json:"server"`
}

// ExampleNewLoader demonstrates creating a config loader with defaults,
// then calling Load to read from disk + env overrides.
func ExampleNewLoader() {
	loader := configkit.NewLoader(
		configkit.Options{AppName: "myapp"},
		func() *AppConfig {
			cfg := &AppConfig{}
			cfg.Server.Host = "localhost"
			cfg.Server.Port = 8080
			return cfg
		},
	)

	cfg, err := loader.Load()
	if err != nil {
		fmt.Printf("load error: %v\n", err)
		return
	}
	fmt.Printf("host=%s port=%d\n", cfg.Server.Host, cfg.Server.Port)
	// Output:
	// host=localhost port=8080
}

// ExampleLoader_Reload demonstrates hot-reloading config from disk.
func ExampleLoader_Reload() {
	loader := configkit.NewLoader(
		configkit.Options{AppName: "myapp"},
		func() *AppConfig {
			cfg := &AppConfig{}
			cfg.Server.Port = 8080
			return cfg
		},
	)

	cfg, _ := loader.Load()
	fmt.Printf("port=%d\n", cfg.Server.Port)
	// Output:
	// port=8080
}
