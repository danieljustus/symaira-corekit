#!/usr/bin/env python3
"""Exercise the real Makefile with isolated formatter discovery and exit codes."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


MAKEFILE = Path(__file__).resolve().parents[1] / "Makefile"
MAKE = shutil.which("make")
# Both /usr/bin/make and Xcode's make are shims; resolve the real GNU Make
# before isolating DEVELOPER_DIR and PATH for the formatter discovery probe.
if sys.platform == "darwin":
    MAKE = subprocess.check_output(["xcrun", "--find", "gnumake"], text=True).strip()


class MakeFormatTests(unittest.TestCase):
    def test_formatter_contract(self):
        cases = (
            # name, xcrun, PATH formatter, override, formatter exit, target
            ("xcode-first", True, True, None, 0, "lint"),
            ("path-fallback", False, True, None, 0, "lint"),
            ("missing", False, False, None, 0, "lint"),
            ("explicit-path-with-spaces", True, True, "custom", 0, "lint"),
            ("invalid-override-no-fallback", True, True, "missing", 0, "lint"),
            ("findings-fail", True, False, None, 1, "lint"),
            ("formatter-error-fails", True, False, None, 23, "lint"),
            ("format", True, False, None, 0, "format"),
            ("format-error-fails", True, False, None, 23, "format"),
        )
        for name, xcode, on_path, override, code, target in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                shutil.copyfile(MAKEFILE, root / "Makefile")
                binaries = root / "bin"
                binaries.mkdir()
                calls = root / "formatter-call"
                developer = str(root / "Selected Xcode.app/Contents/Developer")
                env = {
                    "PATH": str(binaries),
                    "DEVELOPER_DIR": developer,
                    "TEST_CALL_LOG": str(calls),
                    "TEST_FORMAT_EXIT": str(code),
                }

                def executable(path, body):
                    path.write_text("#!/bin/sh\n" + body)
                    path.chmod(0o755)
                    return str(path)

                body = 'printf "%s\\n" "$DEVELOPER_DIR" "$@" > "$TEST_CALL_LOG"\nexit "$TEST_FORMAT_EXIT"\n'
                xcode_formatter = executable(root / "Xcode swift-format", body)
                executable(binaries / "xcrun", 'test "$1" = --find && test "$2" = swift-format || exit 91\n'
                           + (f'printf "%s\\n" "{xcode_formatter}"\n' if xcode else "exit 1\n"))
                if on_path:
                    executable(binaries / "swift-format", body)
                args = [MAKE, target]
                if override:
                    custom = root / "Custom formatter"
                    if override == "custom":
                        executable(custom, body)
                    args.append(f"SWIFT_FORMAT={custom}")
                result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, timeout=10)
                output = result.stdout + result.stderr
                missing = name in {"missing", "invalid-override-no-fallback"}
                self.assertEqual(result.returncode, 2 if missing or code else 0, output)
                if missing:
                    self.assertFalse(calls.exists(), output)
                    self.assertIn("swift-format not found", output)
                    continue
                expected = [developer, target]
                expected += ["--strict"] if target == "lint" else ["--in-place"]
                expected += ["--configuration", ".swift-format", "--recursive", "Sources", "Tests"]
                self.assertEqual(calls.read_text().splitlines(), expected)
                selected = str(root / "Custom formatter") if override else (
                    xcode_formatter if xcode else str(binaries / "swift-format"))
                self.assertIn(selected, output)


if __name__ == "__main__":
    unittest.main()
