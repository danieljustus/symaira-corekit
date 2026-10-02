#!/usr/bin/env python3
"""Record real Go public APIs, replay over TLS 1.3, and reject a mutated fixture.

Cancellation observations compare only the named fields: cancellation identity
(Go errors.Is / Rust cancellation text), cache publication and target content.
Transport-specific wrapped error display text is deliberately not compared.
Go has no context-taking Cosign verifier; Rust process cancellation and rollback
are additional protections tested separately, not claimed as Go parity.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'rust/symaira-core-update/Cargo.toml'
FIXTURE = ROOT / 'testdata/rust-port/fixtures/update/cancellation.json'
TARGET = ROOT / 'target'

def run(command, env):
    result = subprocess.run(command, cwd=ROOT, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
    if result.returncode:
        raise RuntimeError(f'exit {result.returncode}: {command}\n{result.stdout}')
    return result.stdout

def main():
    parser=argparse.ArgumentParser()
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--write', action='store_true')
    group.add_argument('--check', action='store_true')
    args=parser.parse_args()
    env=dict(os.environ, CARGO_TARGET_DIR=str(TARGET))
    metadata=json.loads(run(['cargo','metadata','--offline','--locked','--no-deps','--format-version','1','--manifest-path',str(MANIFEST)],env))
    package=next(p for p in metadata['packages'] if p['name']=='symaira-core-update')
    if Path(package['manifest_path']) != MANIFEST or Path(metadata['workspace_root']) != ROOT or Path(metadata['target_directory']) != TARGET:
        raise RuntimeError('cargo paths escaped candidate')
    sdk=Path.home()/'sdk/go1.26.6/bin/go'
    launcher=os.environ.get('UPDATE_CANCELLATION_GO') or (str(sdk) if sdk.is_file() else shutil.which('go'))
    if not launcher:
        raise RuntimeError('Go launcher is unavailable')
    original_go_env=dict(env,GOTOOLCHAIN='go1.26.6')
    goroot=run([launcher,'env','GOROOT'],original_go_env).strip()
    modules=run([launcher,'env','GOMODCACHE'],original_go_env).strip()
    compiler=str(Path(goroot)/'bin/go')
    if not run([compiler,'version'],dict(env,GOTOOLCHAIN='local')).startswith('go version go1.26.6 '):
        raise RuntimeError('oracle requires pinned go1.26.6')
    with tempfile.TemporaryDirectory(prefix='update-cancellation-gate-') as directory:
        directory=Path(directory)
        for name in ('home','cache','tmp'): (directory/name).mkdir()
        env.update(GOTOOLCHAIN='local',GOMODCACHE=modules,GOCACHE=str(TARGET/'cancellation-go-cache'),GOPROXY='off',GOSUMDB='off',CGO_ENABLED='0')
        binary=directory/('oracle.exe' if os.name=='nt' else 'oracle')
        run([compiler,'build','-o',str(binary),'./scripts/rust-port/update-cancellation-oracle'],env)
        env.setdefault('RUSTUP_HOME',str(Path.home()/'.rustup'))
        env.setdefault('CARGO_HOME',str(Path.home()/'.cargo'))
        env.update(HOME=str(directory/'home'),USERPROFILE=str(directory/'home'),XDG_CACHE_HOME=str(directory/'cache'),TMPDIR=str(directory/'tmp'),TMP=str(directory/'tmp'),TEMP=str(directory/'tmp'))
        recorded=json.loads(run([str(binary)],env))
        if len(recorded)!=16: raise RuntimeError('expected 16 real public-API observations')
        (TARGET/'cancellation-native.json').write_text(json.dumps(recorded,indent=2)+'\n')
        if args.write:
            FIXTURE.write_text(json.dumps(recorded,indent=2)+'\n')
        elif recorded!=json.loads(FIXTURE.read_text()):
            raise RuntimeError('fresh Go observations disagree with fixture: '+json.dumps(recorded,sort_keys=True))
        env['UPDATE_CANCELLATION_FIXTURE']=str(FIXTURE)
        static_command=['cargo','test','--offline','--locked','--manifest-path',str(MANIFEST),'--test','cancellation']
        output=run(static_command,env)
        if 'test result: ok. 2 passed; 0 failed; 2 ignored;' not in output:
            raise RuntimeError('expected two nonzero pre-cancellation/identity tests: '+output)
        mutated=json.loads(json.dumps(recorded));mutated[0]['cancelled']=not mutated[0]['cancelled']
        mutation=directory/'mutated.json';mutation.write_text(json.dumps(mutated))
        negative=subprocess.run(static_command,cwd=ROOT,env=dict(env,UPDATE_CANCELLATION_FIXTURE=str(mutation)),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        if negative.returncode==0 or 'pre-cancellation Go observation mismatch' not in negative.stdout:
            raise RuntimeError('pre-cancelled fixture mutation was not rejected: '+negative.stdout)
        print('PASS real Go recording, two Rust tests and actual pre-cancelled fixture mutation rejection',flush=True)
        helper=directory/'helper'
        helper.mkdir()
        shutil.copy2(binary,helper/('cosign.exe' if os.name=='nt' else 'cosign'))
        env.update(PATH=str(helper)+os.pathsep+env.get('PATH',''),UPDATE_CANCEL_VERIFIER_READY=str(directory/'tmp/verifier-ready'))
        verifier_command=['cargo','test','--offline','--locked','--manifest-path',str(MANIFEST),'--test','cancellation','cancellable_verifier_reaps_native_owned_process_tree','--','--exact','--ignored','--nocapture']
        verifier_output=run(verifier_command,env)
        if 'test result: ok. 1 passed; 0 failed; 0 ignored;' not in verifier_output:
            raise RuntimeError('native owned-process-tree regression did not execute: '+verifier_output)
        print('PASS native owned Cosign process-tree cancellation and reap',flush=True)
        server=subprocess.Popen([str(binary),'serve'],env=env,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            line=server.stdout.readline()
            if not line:
                raise RuntimeError('Go TLS fixture failed to start: '+server.stderr.read())
            connection=json.loads(line)
            env.update(UPDATE_CANCELLATION_URL=connection['url'],UPDATE_CANCELLATION_CERT=connection['cert'],UPDATE_CANCELLATION_FIXTURE=str(FIXTURE))
            command=['cargo','test','--offline','--locked','--manifest-path',str(MANIFEST),'--test','cancellation','public_cancellation_replays_go','--','--exact','--ignored','--nocapture']
            output=run(command,env)
            if 'test result: ok. 1 passed; 0 failed; 0 ignored;' not in output:
                raise RuntimeError('intended nonzero replay did not run: '+output)
            mutated=json.loads(json.dumps(recorded));mutated[0]['cancelled']=not mutated[0]['cancelled']
            mutation=directory/'mutated.json';mutation.write_text(json.dumps(mutated))
            env['UPDATE_CANCELLATION_FIXTURE']=str(mutation)
            negative=subprocess.run(command,cwd=ROOT,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
            if negative.returncode==0 or 'public cancellation observation mismatch' not in negative.stdout:
                raise RuntimeError('actual fixture mutation was not rejected: '+negative.stdout)
            print('PASS 16 Go observations replayed; actual fixture mutation rejected')
        finally:
            server.terminate()
            try: server.wait(timeout=5)
            except subprocess.TimeoutExpired: server.kill();server.wait(timeout=5)

if __name__=='__main__': main()
