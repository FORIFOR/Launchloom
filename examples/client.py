"""Local HTTP integration example, not a separately versioned SDK.

Create: python examples/client.py examples/orbit-brief.json --idempotency-key my-kit-001
Resume: python examples/client.py --campaign CAMPAIGN_ID
No write is automatically retried. Read docs/API.md for permissions and compatibility.
"""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import math
import os
import tempfile
import time
import uuid
import zipfile
from pathlib import Path
from urllib.parse import urlsplit
import httpx


def validate_base(value):
    url = urlsplit(value)
    if url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
        raise ValueError('Use a studio origin without credentials, path, query or fragment')
    loopback = url.hostname == 'localhost'
    try:
        loopback = loopback or ipaddress.ip_address(url.hostname or '').is_loopback
    except ValueError:
        pass
    if not url.hostname or (url.scheme != 'https' and not (url.scheme == 'http' and loopback)):
        raise ValueError('Bearer tokens require HTTPS, except on loopback localhost')
    return value.rstrip('/')


def download_kit(client, campaign, destination):
    """Install only a complete hash-verified ZIP; leave existing files untouched."""
    if destination.exists():
        raise FileExistsError(f'{destination} already exists; choose a new output path')
    path = campaign['outputs']['launch-kit.zip']
    if not path.startswith('/artifacts/'+campaign['id']+'/') or urlsplit(path).netloc:
        raise ValueError('Unexpected artifact origin/path; refusing to forward credentials')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.partial', delete=False) as file:
        temp = Path(file.name)
    try:
        with client.stream('GET', path) as response:
            response.raise_for_status()
            with temp.open('wb') as file:
                for chunk in response.iter_bytes():
                    file.write(chunk)
        with zipfile.ZipFile(temp) as archive:
            if archive.testzip() is not None:
                raise ValueError('Incomplete ZIP')
            manifest = json.loads(archive.read('manifest.json'))
            for name, entry in manifest['files'].items():
                if hashlib.sha256(archive.read(name)).hexdigest() != entry['sha256']:
                    raise ValueError(f'Artifact hash mismatch: {name}')
        # Exclusive creation also protects against a competing download to this path.
        os.link(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('brief', type=Path, nargs='?')
    p.add_argument('--campaign', help='resume this existing id; never create another campaign')
    p.add_argument('--idempotency-key', help='reuse this key with the same brief after a lost create response')
    p.add_argument('--options', type=Path)
    p.add_argument('--capture', type=Path)
    p.add_argument('--audio', type=Path)
    p.add_argument('--rights-confirmed', action='store_true')
    p.add_argument('--approve-plan', action='store_true', help='explicitly approve the saved storyboard and render')
    p.add_argument('--retry-build', action='store_true', help='explicitly retry a failed/interrupted build with its original options')
    p.add_argument('--download', type=Path, help='save and hash-check the ready kit to a new file')
    p.add_argument('--wait-seconds', type=float, default=180)
    p.add_argument('--base', default='http://127.0.0.1:8787')
    args = p.parse_args(argv)
    if bool(args.brief) == bool(args.campaign):
        p.error('Supply either a brief JSON file or --campaign, not both')
    if not math.isfinite(args.wait_seconds) or args.wait_seconds <= 0:
        p.error('--wait-seconds must be finite and positive')
    if args.campaign and args.idempotency_key:
        p.error('--idempotency-key is for creation; --campaign already identifies the saved work')
    try:
        base = validate_base(args.base)
    except ValueError as error:
        p.error(str(error))
    token = os.getenv('LAUNCHLOOM_TOKEN')
    if not token:
        token_path = Path(os.getenv('LAUNCHLOOM_DATA', '.launchloom'))/'access-token'
        if not token_path.exists():
            p.error('Set LAUNCHLOOM_TOKEN or start the local studio first')
        token = token_path.read_text().strip()
    if (args.capture or args.audio) and not args.rights_confirmed:
        p.error('Confirm rights with --rights-confirmed before uploading media')
    cid = args.campaign
    with httpx.Client(base_url=base, headers={'Authorization': 'Bearer '+token},
                      timeout=120, follow_redirects=False, trust_env=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        if not cid:
            key = args.idempotency_key or str(uuid.uuid4())
            print('Creation key:', key, '(keep this key if the response is lost)', flush=True)
            data = request('POST', '/api/campaigns', json=json.loads(args.brief.read_text()),
                           headers={'Idempotency-Key': key})
            cid = data['id']
        print('Campaign:', cid, flush=True)
        print('Resume:', f'python examples/client.py --base {base} --campaign {cid}', flush=True)
        print('Review:', f'{base}/?campaign={cid}', flush=True)
        data = request('GET', '/api/campaigns/'+cid)
        if data['state'] == 'draft':
            options = json.loads(args.options.read_text()) if args.options else {'capture_mode':'none', 'review_plan':True}
            if args.capture:
                options['capture_mode'] = 'upload'
            for kind, path in [('capture', args.capture), ('audio', args.audio)]:
                if path:
                    with path.open('rb') as file:
                        request('POST', f'/api/campaigns/{cid}/media?kind={kind}&rights_confirmed=true',
                                content=file, headers={'Content-Type':'application/octet-stream'})
            request('POST', f'/api/campaigns/{cid}/build', json=options)
        elif args.options or args.capture or args.audio:
            p.error('This campaign already started. Resume without new options/media; start a new intent to change them')
        if args.retry_build and data['state'] in {'failed','interrupted'}:
            request('POST', f'/api/campaigns/{cid}/build', json=data['options'])
        deadline = time.monotonic()+args.wait_seconds
        while time.monotonic() < deadline:
            data = request('GET', '/api/campaigns/'+cid)
            print(data['state'], data['stage'], data['progress'], flush=True)
            if data['state'] == 'ready':
                if args.download:
                    download_kit(client, data, args.download)
                    print('Verified kit:', args.download)
                else:
                    print('Kit:', base+data['outputs']['launch-kit.zip'], '(local authentication required)')
                return 0
            if data['state'] == 'awaiting_review':
                if not args.approve_plan:
                    print('Waiting for review. Save edits in the studio, then render there or resume this id with --approve-plan.')
                    return 2
                request('POST', f'/api/campaigns/{cid}/render')
                args.approve_plan = False
            elif data['state'] in {'failed','interrupted'}:
                print('Build stopped:', data['error'], '\nInspect the cause; use --campaign with --retry-build only after review.')
                return 1
            time.sleep(min(1, max(0, deadline-time.monotonic())))
        print('Outcome not yet confirmed. The server may still be working; resume this id. No cancellation was sent.')
        return 3


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (httpx.HTTPError, OSError, ValueError, zipfile.BadZipFile) as error:
        # Never include a response body, bearer token or private input in an error log.
        print(f'Client stopped ({type(error).__name__}). Inspect the studio; resume the printed campaign id or reuse the creation key. No write was retried.')
        raise SystemExit(1)
