#!/usr/bin/env python3
"""Passive macOS demo CPU experiment. No input injection, no production agents.

Runs a fresh process per sample. Fixed 1000x680 minimum window, dark mode,
3 s warm-up, 6 s CPU-time window. Three launches per mode are an exploratory
baseline, not a battery/GPU energy claim. Increase --repeats for publication.
All process lifetime and raw samples are recorded; only owned PIDs are stopped.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import time


def cpu_seconds(pid):
    value = subprocess.check_output(['ps', '-p', str(pid), '-o', 'time='], text=True).strip()
    parts = [float(x) for x in value.split(':')]
    result = 0.0
    for part in parts:
        result = result * 60 + part
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('app', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--repeats', type=int, default=3)
    args = p.parse_args()
    exe = args.app / 'Contents/MacOS/LiquidTopographyDemo'
    modes = ['off', 'static', 'idle', 'interaction', 'hidden']
    report = {'binary_sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
              'warmup_seconds': 3, 'sample_seconds': 6, 'samples': []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for repeat in range(args.repeats):
        for mode in (modes if repeat % 2 == 0 else list(reversed(modes))):
            env = dict(os.environ, SYMAIRA_TOPO_BENCHMARK=mode)
            log = args.output.with_name(f'{args.output.stem}-{repeat}-{mode}.log')
            with log.open('wb') as stream:
                proc = subprocess.Popen([str(exe), '-ApplePersistenceIgnoreState', 'YES'],
                                        env=env, stdout=stream, stderr=stream)
                try:
                    time.sleep(3)
                    if proc.poll() is not None:
                        raise RuntimeError(f'{mode}: exited {proc.returncode}; see {log}')
                    if mode == 'hidden' and 'TOPO_BENCH hidden=1 visible=0' not in log.read_text():
                        raise RuntimeError(f'Window did not become hidden; see {log}')
                    before = cpu_seconds(proc.pid)
                    start = time.monotonic()
                    time.sleep(6)
                    after = cpu_seconds(proc.pid)
                    elapsed = time.monotonic() - start
                    row = {'mode': mode, 'repeat': repeat, 'cpu_seconds': after-before,
                           'elapsed_seconds': elapsed, 'cpu_percent': 100*(after-before)/elapsed}
                    report['samples'].append(row)
                    args.output.write_text(json.dumps(report, indent=2)+'\n')
                    print(mode, repeat, round(row['cpu_percent'], 2), flush=True)
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=5)
    report['summary'] = {mode: {
        'median_cpu_percent': statistics.median(r['cpu_percent'] for r in report['samples'] if r['mode']==mode),
        'min_cpu_percent': min(r['cpu_percent'] for r in report['samples'] if r['mode']==mode),
        'max_cpu_percent': max(r['cpu_percent'] for r in report['samples'] if r['mode']==mode),
        'n': sum(r['mode']==mode for r in report['samples'])} for mode in modes}
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
