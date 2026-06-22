package fsutil

import (
	"errors"
	"strings"
	"testing"
)

func TestValidatePath_Valid(t *testing.T) {
	valid := []string{
		"foo",
		"foo/bar",
		"foo/bar/baz.txt",
		"a",
		"foo.bar",
		"my-file_2.txt",
		"dir/subdir/file",
		"a/b/c/d/e",
		"f",
	}
	for _, p := range valid {
		if err := ValidatePath(p); err != nil {
			t.Errorf("ValidatePath(%q) = %v, want nil", p, err)
		}
	}
}

func TestValidatePath_Empty(t *testing.T) {
	if err := ValidatePath(""); err == nil {
		t.Error("ValidatePath(\"\") = nil, want error")
	}
}

func TestValidatePath_NullByte(t *testing.T) {
	if err := ValidatePath("foo\x00bar"); err == nil {
		t.Error("ValidatePath with null byte = nil, want error")
	}
}

func TestValidatePath_ControlChar(t *testing.T) {
	for i := rune(1); i < 0x20; i++ {
		p := "foo" + string(i) + "bar"
		if err := ValidatePath(p); err == nil {
			t.Errorf("ValidatePath with control char 0x%02x = nil, want error", i)
		}
	}
}

func TestValidatePath_TabAndNewlineRejected(t *testing.T) {
	for _, p := range []string{"foo\tbar", "foo\nbar"} {
		if err := ValidatePath(p); err == nil {
			t.Errorf("ValidatePath(%q) = nil, want error (tab/newline must be rejected)", p)
		}
	}
}

func TestValidatePath_Traversal(t *testing.T) {
	traversal := []string{
		"../foo",
		"foo/../bar",
		"foo/..",
		"../../etc/passwd",
		"foo/../../../etc/passwd",
	}
	for _, p := range traversal {
		if err := ValidatePath(p); err == nil {
			t.Errorf("ValidatePath(%q) = nil, want traversal error", p)
		}
	}
}

func TestValidatePath_Absolute(t *testing.T) {
	abs := []string{
		"/foo",
		"/etc/passwd",
		"/",
	}
	for _, p := range abs {
		if err := ValidatePath(p); err == nil {
			t.Errorf("ValidatePath(%q) = nil, want absolute path error", p)
		}
	}
}

func TestValidatePath_DoubleSlash(t *testing.T) {
	doubleSlash := []string{
		"foo//bar",
		"foo///bar",
		"//foo",
	}
	for _, p := range doubleSlash {
		if err := ValidatePath(p); err == nil {
			t.Errorf("ValidatePath(%q) = nil, want double slash error", p)
		}
	}
}

func TestValidatePath_WindowsBackslashTraversal(t *testing.T) {
	err := ValidatePath(`..\..\etc\passwd`)
	if err == nil {
		t.Error("ValidatePath with backslash traversal = nil, want error")
	}
}

func TestValidatePath_ErrorsAreWrappable(t *testing.T) {
	err := ValidatePath("")
	if !errors.Is(err, ErrInvalidPath) {
		t.Errorf("ValidatePath(\"\") error is not ErrInvalidPath: %v", err)
	}
}

func TestHasTraversal(t *testing.T) {
	tests := []struct {
		path string
		want bool
	}{
		{"foo/bar", false},
		{"foo/../bar", true},
		{"../foo", true},
		{"foo/..", true},
		{"foo", false},
		{"", false},
		{"/etc/passwd", false},
		{"foo/../../etc", true},
	}
	for _, tt := range tests {
		got := HasTraversal(tt.path)
		if got != tt.want {
			t.Errorf("HasTraversal(%q) = %v, want %v", tt.path, got, tt.want)
		}
	}
}

func TestValidatePath_AllControlChars(t *testing.T) {
	if err := ValidatePath("\x00"); err == nil {
		t.Error("ValidatePath(\"\\x00\") = nil, want error")
	}

	for i := 1; i < 0x20; i++ {
		p := string(rune(i))
		if err := ValidatePath(p); err == nil {
			if !strings.Contains(err.Error(), "control character") {
				t.Errorf("ValidatePath with 0x%02x error doesn't mention control char: %v", i, err)
			}
		}
	}
}
