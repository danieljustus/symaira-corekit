package versionkit_test

import (
	"fmt"

	"github.com/danieljustus/symaira-corekit/versionkit"
)

func ExampleNew() {
	info := versionkit.New("symfetch", "v0.11.0", 1)
	fmt.Println(info.String())
	// Output: symfetch v0.11.0
}
