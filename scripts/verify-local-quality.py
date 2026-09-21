"""Offline quality runner: preserves command outputs, exit codes and source hashes."""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]


def main(output):
    output.mkdir(parents=True,exist_ok=True)
    env={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','SYSTEMROOT','LANG') if k in os.environ}
    env['PYTHONPATH']=str(ROOT)
    files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
           for folder in ('launchloom','tests','examples','scripts') for p in (ROOT/folder).rglob('*')
           if p.suffix in {'.py','.js','.css','.html'} and '__pycache__' not in p.parts}
    report={'revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        'environment':{'os':platform.platform(),'cpu':platform.machine(),'python':sys.version,
            'packages':{name:importlib.metadata.version(name) for name in ('fastapi','uvicorn','pydantic','httpx','Pillow','playwright','numpy','pytest')}},
        'runs':[]}
    (output/'source-files.json').write_text(json.dumps(files,indent=2,sort_keys=True))
    def run(name,command,*,cwd=ROOT,process_env=env,timeout=360):
        started=time.monotonic()
        completed=subprocess.run(command,cwd=cwd,env=process_env,capture_output=True,text=True,timeout=timeout)
        log=output/(name+'.log');log.write_text(completed.stdout+completed.stderr)
        result={'name':name,'command':command,'cwd':str(cwd),'exit_code':completed.returncode,
            'status':'PASS' if completed.returncode==0 else 'FAIL','seconds':round(time.monotonic()-started,2),
            'evidence':str(log.relative_to(output))}
        report['runs'].append(result)
        (output/'report.json').write_text(json.dumps(report,indent=2))
        print(name,result['status'],f"exit={completed.returncode}",flush=True)
        return completed.returncode==0
    run('compile',[sys.executable,'-m','compileall','-q','launchloom','examples','tests','scripts'])
    for path in sorted((ROOT/'launchloom').rglob('*.js')):
        run('syntax-'+path.stem,['node','--check',str(path)])
    run('pytest',[sys.executable,'-m','pytest','-q','--junitxml='+str(output/'pytest.xml')])
    run('wheel',[sys.executable,'-m','pip','wheel','.','--no-deps','--no-build-isolation','--no-index','--wheel-dir',str(output/'wheel')])
    wheels=list((output/'wheel').glob('launchloom-*.whl'))
    if len(wheels)==1:
        with tempfile.TemporaryDirectory(prefix='launchloom-wheel-') as tmp:
            target=Path(tmp)/'site'
            if run('wheel-install',[sys.executable,'-m','pip','install','--no-index','--no-deps','--target',str(target),str(wheels[0])],cwd=Path(tmp)):
                smoke_env={**env,'PYTHONPATH':str(target)}
                code="""from pathlib import Path
import launchloom
from launchloom.config import Settings
from launchloom.server import create_app
from fastapi.testclient import TestClient
assert 'site/launchloom' in str(Path(launchloom.__file__).as_posix())
settings=Settings(data_dir=Path('data'),token='offline-installed-wheel-token')
with TestClient(create_app(settings,run_worker=False)) as client:
 assert client.get('/').status_code==200
 assert client.get('/static/app.js').status_code==200
 client.headers['Authorization']='Bearer '+settings.token
 assert client.get('/api/openapi.json').status_code==200
 assert client.post('/api/demo?review_plan=true',headers={'Idempotency-Key':'wheel-intent-001'}).json()['options']['review_plan']
print('Installed wheel serves UI, typed API and durable reviewed sample; no worker or external provider ran.')
"""
                run('installed-smoke',[sys.executable,'-c',code],cwd=Path(tmp),process_env=smoke_env)
    report['runs'].append({'name':'static-typecheck','status':'NOT_APPLICABLE','exit_code':None,
        'observed':'No configured Python/JS static typechecker. Compile/syntax/runtime schema tests are reported separately.'})
    report['exit_code']=int(any(r['status']=='FAIL' for r in report['runs']))
    (output/'report.json').write_text(json.dumps(report,indent=2))
    return report['exit_code']


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=Path('/tmp/launchloom-quality'))
    args=parser.parse_args();raise SystemExit(main(args.output.resolve()))
