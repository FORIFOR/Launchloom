"""Produce a kit from JSON. Requires a running local studio. Does NOT publish.
Usage: python examples/client.py examples/orbit-brief.json --options options.json
"""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path
import httpx

def main():
    p=argparse.ArgumentParser();p.add_argument('brief',type=Path);p.add_argument('--options',type=Path);p.add_argument('--capture',type=Path);p.add_argument('--audio',type=Path);p.add_argument('--rights-confirmed',action='store_true');p.add_argument('--approve-plan',action='store_true',help='render the generated storyboard without reading it');p.add_argument('--base',default='http://127.0.0.1:8787');args=p.parse_args()
    token=os.getenv('LAUNCHLOOM_TOKEN')
    if not token:
        token_path=Path(os.getenv('LAUNCHLOOM_DATA','.launchloom'))/'access-token'
        if not token_path.exists():p.error('Set LAUNCHLOOM_TOKEN or start the local studio first')
        token=token_path.read_text().strip()
    if (args.capture or args.audio) and not args.rights_confirmed:p.error('Confirm rights with --rights-confirmed before uploading media')
    options=json.loads(args.options.read_text()) if args.options else {'capture_mode':'none'}
    if args.capture:options['capture_mode']='upload'
    with httpx.Client(base_url=args.base,headers={'Authorization':'Bearer '+token},timeout=120) as c:
        r=c.post('/api/campaigns',json=json.loads(args.brief.read_text()));r.raise_for_status();cid=r.json()['id']
        for kind,path in [('capture',args.capture),('audio',args.audio)]:
            if path:
                with path.open('rb') as f:r=c.post(f'/api/campaigns/{cid}/media?kind={kind}&rights_confirmed=true',content=f,headers={'Content-Type':'application/octet-stream'})
                r.raise_for_status()
        r=c.post(f'/api/campaigns/{cid}/build',json=options);r.raise_for_status()
        deadline=time.monotonic()+3600
        while time.monotonic()<deadline:
            r=c.get('/api/campaigns/'+cid);r.raise_for_status();data=r.json()
            print(data['state'],data['stage'],data['progress'],flush=True)
            if data['state']=='ready':print('Kit:',args.base+data['outputs']['launch-kit.zip']);return
            if data['state']=='awaiting_review':
                # Nothing has been rendered and no provider has been contacted yet.
                if not args.approve_plan:
                    print('Waiting for a storyboard review. Open the studio to read and reword it,');
                    print('or re-run with --approve-plan to render it as generated.');return
                c.post(f'/api/campaigns/{cid}/render').raise_for_status()
            if data['state'] in {'failed','interrupted'}:raise RuntimeError(data['error'])
            time.sleep(3)
        raise TimeoutError('Client stopped waiting; inspect the studio before retrying')
if __name__=='__main__':main()
