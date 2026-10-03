"""Bounded byte capture for owned, descendant-free contract fixture processes."""
from __future__ import annotations

import queue
import subprocess
import threading
import time

OUTPUT_LIMIT = 2 * 1024 * 1024


def exchange(command, stdin, env, timeout, *, serial=False, limit=OUTPUT_LIMIT):
    """Capture each stream within its cap and reap on overflow or deadline.

    ponytail: these fixture binaries do not spawn descendants. Before using
    this helper for arbitrary commands, add native process-tree ownership.
    """
    deadline = time.monotonic() + timeout
    condition = threading.Condition()
    outputs = [bytearray(), bytearray()]
    ended = [False, False, False]
    failures = []
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, bufsize=0)
    assert process.stdin is not None and process.stdout is not None and process.stderr is not None
    sink, source, errors = process.stdin, process.stdout, process.stderr

    def fail(error):
        with condition:
            failures.append(error)
            condition.notify_all()

    def read(stream, index):
        try:
            while True:
                # Read at most the remaining capacity plus one overflow byte.
                chunk = stream.read(min(65536, limit - len(outputs[index]) + 1))
                if not chunk:
                    break
                with condition:
                    if len(chunk) > limit - len(outputs[index]):
                        raise ValueError(f"fixture {'stdout' if index == 0 else 'stderr'} exceeds its capture bound")
                    outputs[index].extend(chunk)
                    condition.notify_all()
        except Exception as error:
            fail(error)
        finally:
            with condition:
                ended[index] = True
                condition.notify_all()

    def write():
        try:
            lines = stdin.split(b"\n")
            parts = [line + b"\n" for line in lines[:-1]]
            if lines[-1]:
                parts.append(lines[-1])
            for index, part in enumerate(parts if serial else [stdin]):
                remaining = memoryview(part)
                while remaining:
                    written = sink.write(remaining)
                    if not written:
                        raise BrokenPipeError("fixture input closed")
                    remaining = remaining[written:]
                if serial:
                    with condition:
                        while outputs[0].count(b"\n") <= index:
                            if failures:
                                return
                            if ended[0]:
                                raise ValueError("MCP process ended before its next response")
                            left = deadline - time.monotonic()
                            if left <= 0:
                                raise queue.Empty()
                            condition.wait(left)
        except BrokenPipeError:
            # communicate() likewise accepts a fixture closing input early.
            if serial:
                fail(ValueError("MCP process ended before its next response"))
        except Exception as error:
            fail(error)
        finally:
            sink.close()
            with condition:
                ended[2] = True
                condition.notify_all()

    threads = [threading.Thread(target=read, args=(source, 0), daemon=True),
               threading.Thread(target=read, args=(errors, 1), daemon=True),
               threading.Thread(target=write, daemon=True)]
    try:
        for thread in threads:
            thread.start()
        with condition:
            while True:
                if failures:
                    raise failures[0]
                if process.poll() is not None and all(ended):
                    return process.returncode, bytes(outputs[0]), bytes(outputs[1])
                left = deadline - time.monotonic()
                if left <= 0:
                    if serial:
                        raise queue.Empty()
                    raise subprocess.TimeoutExpired(command, timeout)
                condition.wait(min(left, 0.02))
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        with condition:
            # Wake the serial writer after termination, without new signals.
            if not all(ended):
                failures.append(ValueError("fixture exchange stopped"))
            condition.notify_all()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=1)
        for stream in (sink, source, errors):
            stream.close()
        if any(thread.is_alive() for thread in threads):
            raise RuntimeError("owned fixture pipe did not close after termination")
