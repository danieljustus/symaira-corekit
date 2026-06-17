package fsutil

import (
	"os"
	"path/filepath"
)

// writeTempThenRename writes data to a unique temporary file in the same
// directory as path, fsyncs it, closes it, and then hands the temp path to
// rename to atomically move it into place. On any error the temporary file is
// removed. The only platform-specific behavior is the rename step.
func writeTempThenRename(path string, data []byte, perm os.FileMode, rename func(tmp, dst string) error) error {
	f, err := os.CreateTemp(filepath.Dir(path), filepath.Base(path)+".tmp-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	if err := f.Chmod(perm); err != nil {
		_ = f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if _, err := f.Write(data); err != nil {
		_ = f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := f.Sync(); err != nil {
		_ = f.Close()
		_ = os.Remove(tmp)
		return err
	}
	if err := f.Close(); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	if err := rename(tmp, path); err != nil {
		_ = os.Remove(tmp)
		return err
	}
	return nil
}
