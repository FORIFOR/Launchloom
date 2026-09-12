from __future__ import annotations
import argparse
import os
import shutil
import sys
import time
from pathlib import Path

def load_env(path: Path = Path('.env')):
    """Read literal KEY=value pairs, without shell expansion or executing code."""
    if not path.is_file(): return
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line: raise ValueError('Invalid .env line: use KEY=value')
        key,value=line.split('=',1);key=key.strip();value=value.strip()
        if not key.replace('_','').isalnum():raise ValueError('Invalid .env variable name')
        if len(value)>=2 and value[0]==value[-1] and value[0] in "\"'":value=value[1:-1]
        os.environ.setdefault(key,value)

def main():
    load_env()
    from .config import Settings
    parser=argparse.ArgumentParser(description='Launchloom — local-first product launch studio')
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve');serve.add_argument('--host');serve.add_argument('--port',type=int)
    sub.add_parser('doctor');sub.add_parser('demo')
    args=parser.parse_args();s=Settings()
    if args.command=='doctor':
        import importlib.metadata
        for binary in ['ffmpeg','ffprobe']:print(f'{binary}: {shutil.which(binary) or "MISSING"}')
        from .capture import browser_status
        path,ready,problem=browser_status(s)
        source='CHROMIUM_EXECUTABLE / system' if s.chromium else 'Playwright managed'
        print(f'Chromium ({source}): {path or "not resolved"}')
        print('Browser launch:','OK' if ready else 'FAILED — '+problem)
        from .rendering import font_source
        for bold in (False,True):
            path,cjk=font_source(bold)
            label='Bold font' if bold else 'Text font'
            print(f'{label}: {path or "Pillow built-in bitmap font"}' + ('' if cjk else '  <- no Japanese coverage; set LAUNCHLOOM_FONT/LAUNCHLOOM_FONT_BOLD'))
        for package in ['fastapi','playwright','Pillow','pydantic']:print(f'{package}: {importlib.metadata.version(package)}')
        print('Chromium sandbox:', 'DISABLED — trusted staging only' if s.no_sandbox else 'enabled')
        print('Live publishing:',s.enable_live_publish,'| Paid video generation:',s.enable_paid_generation)
        return
    s.prepare()
    if args.command=='demo':
        import httpx
        try:
            with httpx.Client(base_url=s.base_url,headers={'Authorization':'Bearer '+s.token},timeout=30) as client:
                r=client.post('/api/demo');r.raise_for_status();cid=r.json()['id'];last=''
                while True:
                    r=client.get('/api/campaigns/'+cid);r.raise_for_status();c=r.json()
                    message=f"{c['progress']:3}% {c['stage']} / {c['state']}"
                    if message!=last:print(message,flush=True);last=message
                    if c['state']=='ready':print('Launch kit:',s.data_dir/'campaigns'/cid/'launch-kit.zip');return
                    if c['state'] in {'failed','interrupted'}:raise RuntimeError(c['error'])
                    time.sleep(2)
        except Exception as e:print('Demo failed:',e,'\nStart the studio with: python -m launchloom serve',file=sys.stderr);sys.exit(1)
    if args.host:s.host=args.host
    if args.port:s.port=args.port
    from .server import create_app
    import uvicorn
    print(f'\nLaunchloom → http://{s.host}:{s.port}\nLocal access key: {s.token}\nData: {s.data_dir}\n',flush=True)
    if s.host not in {'127.0.0.1','localhost'}:print('Network binding enabled: use TLS, host allowlisting and isolation. This is a single-operator alpha.',flush=True)
    uvicorn.run(create_app(s),host=s.host,port=s.port,workers=1,access_log=False)
