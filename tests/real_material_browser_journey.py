"""Opt-in, installed-wheel real-material acceptance. No production changes.

Requires an operator-supplied authorized source, exact SHA-256 and provenance.
This is separate from the offline synthetic first-success regression. External
navigation is limited to read-only CTA checks on the two public product repos.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
from importlib.resources import files
import json
import os
from pathlib import Path
import platform
import signal
import socket
import sqlite3
import subprocess
import sys
import time
import traceback
import zipfile

from first_success_browser_journey import ROOT, TOKEN, serve
import launchloom
import httpx
from playwright.sync_api import sync_playwright, expect

GENIE_URL = 'https://github.com/FORIFOR/genie'
LAUNCHLOOM_URL = 'https://github.com/FORIFOR/Launchloom'
SHAPES = {'landscape': (1920, 1080), 'portrait': (1080, 1920)}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def probe_video(path, shape=None, seconds=None):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    meta = json.loads(result.stdout)
    video = next(s for s in meta['streams'] if s['codec_type'] == 'video')
    if shape is not None:
        assert (video['width'], video['height']) == shape, video
        assert video['codec_name'] == 'h264' and video['pix_fmt'] == 'yuv420p', video
        assert video['avg_frame_rate'] == '30/1', video
    if seconds is not None:
        assert abs(float(meta['format']['duration']) - seconds) < .15, meta['format']
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'],
                             capture_output=True, text=True, timeout=120)
    assert decoded.returncode == 0 and not decoded.stderr.strip(), decoded.stderr
    return {'sha256': sha256(path), 'bytes': Path(path).stat().st_size,
            'width': video['width'], 'height': video['height'], 'codec': video['codec_name'],
            'fps': video['avg_frame_rate'], 'duration': float(meta['format']['duration']),
            'audio_streams': sum(s['codec_type'] == 'audio' for s in meta['streams']),
            'full_decode': True}


def validate_kit(kit, dest, *, cid, revision, brand, url, title, caption, seconds):
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(kit) as archive:
        assert archive.testzip() is None
        names = set(archive.namelist())
        required = {'landscape.mp4', 'portrait.mp4', 'captions.srt', 'storyboard.json',
                    'campaign.json', 'posts.json', 'social-copy.md', 'site/index.html',
                    'site/site.css', 'site/site.js', 'LICENSE', 'NOTICE', 'site/LICENSE', 'site/NOTICE'}
        assert required <= names, names
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['campaign_id'] == cid and manifest['revision'] == revision
        assert set(manifest['files']) == names - {'manifest.json'}
        for name, entry in manifest['files'].items():
            content = archive.read(name)
            assert hashlib.sha256(content).hexdigest() == entry['sha256'], name
            assert len(content) == entry['bytes'], name
            assert b'PRIVATE-HD-ACCEPTANCE' not in content, name
        assert not any(n.startswith(('input/', 'capture/')) or n in {'brief.json', 'access-token'} for n in names)
        storyboard = json.loads(archive.read('storyboard.json'))
        assert storyboard['scenes'][0]['title'] == title
        assert storyboard['scenes'][0]['caption'] == caption
        assert caption in archive.read('captions.srt').decode()
        html = archive.read('site/index.html').decode()
        assert brand in html and url in html and 'class="button primary cta"' in html
        for name in ('LICENSE', 'NOTICE'):
            expected = files('launchloom').joinpath('licenses', name).read_bytes()
            assert archive.read(name) == archive.read('site/' + name) == expected
        media = {}
        for ratio, shape in SHAPES.items():
            film = dest / (ratio + '.mp4')
            film.write_bytes(archive.read(ratio + '.mp4'))
            media[ratio] = probe_video(film, shape, seconds)
            assert (manifest['videos'][ratio]['width'], manifest['videos'][ratio]['height']) == shape
            # Preserve visual evidence at opening, product proof and CTA phases.
            for label, when in [('opening', 1), ('proof', seconds / 2), ('closing', seconds - 1)]:
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', str(when), '-i', str(film),
                                '-frames:v', '1', str(dest / f'{ratio}-{label}.png')], check=True, timeout=30)
        # Local evidence extraction does not alter or republish the downloaded kit.
        for name in names:
            target = dest / name
            assert target.resolve().is_relative_to(dest.resolve()), name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return {'kit_sha256': sha256(kit), 'members': len(names), 'media': media}


def main(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(), 'revision': args.revision,
              'checks': [], 'status': 'RUNNING', 'command': [sys.executable, *sys.argv],
              'test_sha256': sha256(Path(__file__)), 'application_path': str(Path(launchloom.__file__).resolve()),
              'platform': platform.platform(), 'python': sys.version, 'page_errors': [],
              'limits': ['Genie source is an existing edited demo, not fresh current-version capture.',
                         'Source detail is normalized to 1280x800 before HD composition.',
                         'Portrait output embeds a landscape proof panel; HD size is not mobile legibility acceptance.',
                         'Captions are SRT sidecars; standard LP/social copy remains based on the brief.',
                         'Silent output; no audio production, publishing, paid service, sales or human usability claim.']}
    report['required_checks'] = {name: 'NOT_RUN' for name in (
        'wheel-byte-identity', 'source-identity', 'installed-wheel', 'served-wheel-identity',
        'second-real-source', 'genie-review-restart', 'genie-hd-export', 'genie-cta',
        'genie-real-revision', 'launchloom-review-restart', 'launchloom-hd-export',
        'launchloom-cta', 'two-brand-final-restart')}
    process = None
    page = None
    browser = None
    def record(name, detail):
        if name in report['required_checks']: report['required_checks'][name] = 'PASS'
        report['checks'].append({'id': name, 'status': 'PASS', 'observed': detail})
        print(name, json.dumps(detail, ensure_ascii=False), flush=True)
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    try:
        if sys.flags.optimize: raise RuntimeError('Assertions must be enabled')
        assert os.getenv('LAUNCHLOOM_TEST_INSTALLED') == '1', 'This acceptance must run from an installed wheel'
        assert not Path(launchloom.__file__).resolve().is_relative_to(ROOT), 'Source checkout was imported'
        with zipfile.ZipFile(args.wheel) as archive:
            members = [n for n in archive.namelist() if n.startswith('launchloom/') and not n.endswith('/')]
            assert members
            installed_root = Path(launchloom.__file__).resolve().parent.parent
            for name in members:
                assert (installed_root / name).read_bytes() == archive.read(name), name
        record('wheel-byte-identity', {'wheel_sha256': sha256(args.wheel), 'matched_application_files': len(members)})
        assert args.source.is_file() and sha256(args.source) == args.source_sha256, 'Source identity mismatch'
        assert args.source_provenance.strip(), 'Rights/provenance description is required'
        source_meta = probe_video(args.source)
        assert (source_meta['width'], source_meta['height']) == (1920, 1080)
        assert source_meta['duration'] >= 23
        record('source-identity', {'file': args.source.name, 'provenance': args.source_provenance, **source_meta})
        record('installed-wheel', {name: importlib.metadata.version(name) for name in
                                  ('launchloom', 'fastapi', 'uvicorn', 'pydantic', 'Pillow', 'playwright', 'numpy')})
        data = output / 'private-studio-data'
        data.mkdir()
        sock = socket.socket(); sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]; sock.close()
        base = f'http://127.0.0.1:{port}'
        env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'SYSTEMROOT', 'LANG',
                                         'PLAYWRIGHT_BROWSERS_PATH', 'CHROMIUM_EXECUTABLE') if k in os.environ}
        env['LAUNCHLOOM_TEST_INSTALLED'] = '1'
        def stop_server():
            nonlocal process
            if process and process.poll() is None:
                process.terminate()
                try: process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=10)
        def start_server():
            nonlocal process
            with (output / 'server.log').open('a') as log:
                process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', str(data),
                                            '--port', str(port)], cwd=data, env=env, stdout=log,
                                           stderr=subprocess.STDOUT, start_new_session=True)
            with httpx.Client(trust_env=False) as client:
                for _ in range(150):
                    if process.poll() is not None: raise AssertionError('Server exited; see server.log')
                    try:
                        if client.get(base + '/healthz', timeout=.5).status_code == 200: return
                    except httpx.HTTPError: pass
                    time.sleep(.1)
            raise AssertionError('Server startup timeout')
        start_server()
        with httpx.Client(base_url=base, headers={'Authorization': 'Bearer ' + TOKEN}, trust_env=False, timeout=60) as api:
            for route, relative in [('/', 'web/index.html'), ('/static/app.js', 'web/app.js')]:
                response = api.get(route); response.raise_for_status()
                assert response.content == files('launchloom').joinpath(relative).read_bytes(), route
            record('served-wheel-identity', 'Studio HTML and JavaScript match installed wheel bytes')
            def snapshot(cid):
                r = api.get('/api/campaigns/' + cid); r.raise_for_status(); return r.json()
            def ids(): return {c['id'] for c in api.get('/api/campaigns').json()}
            with sync_playwright() as pw:
                try:
                    browser = pw.chromium.launch(executable_path=args.browser_executable,
                                                 channel=None if args.browser_executable else 'chrome',
                                                 chromium_sandbox=True, headless=True)
                    report['browser'] = {'version': browser.version, 'sandbox': True}
                    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='ja-JP')
                    context.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                    page = context.new_page()
                    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
                    page.goto(base)
                    page.locator('#access-token').fill(TOKEN)
                    page.locator('#access-form button').click()
                    page.locator('#access-dialog').wait_for(state='hidden')

                    # Independent second product source: live Launchloom standard UI,
                    # captured from the installed wheel, not a recolored Genie clone.
                    recording = browser.new_context(viewport={'width': 1920, 'height': 1080},
                        storage_state=context.storage_state(), locale='ja-JP',
                        record_video_dir=str(output / 'second-source'), record_video_size={'width': 1920, 'height': 1080})
                    recording.route('**/*', lambda route: route.continue_() if route.request.url.startswith(base + '/') else route.abort())
                    rp = recording.new_page(); rp.goto(base)
                    rp.locator('#first-success-title').wait_for(); rp.wait_for_timeout(1000)
                    rp.locator('.first-success details > summary').click()
                    rp.locator('.first-success [data-new]').click()
                    rp.locator('[name="name"]').fill('Launchloom')
                    rp.locator('[name="tagline"]').fill('動画・紹介ページ・SNS原稿を、ひとつの企画から。')
                    rp.locator('[name="audience"]').fill('自分のプロダクトを紹介する制作者')
                    rp.locator('[name="features"]').fill('企画を入力 | 入力内容を確認してから制作します | このローカル画面で確認')
                    rp.wait_for_timeout(4000)
                    rp.locator('#capture-mode').select_option('upload')
                    rp.wait_for_timeout(3000)
                    rp.locator('[data-close="create-dialog"]').click()
                    rp.wait_for_timeout(2000)
                    second_video = rp.video
                    recording.close()
                    second_source = output / 'launchloom-standard-ui-source.webm'
                    second_video.save_as(str(second_source))
                    second_meta = probe_video(second_source)
                    assert second_meta['duration'] >= 10 and ids() == set()
                    record('second-real-source', {'source': second_source.name, 'provenance': 'Live installed Launchloom UI; Apache-2.0 application; disposable QA brief only.', **second_meta})

                    def fill_form(brand, tagline, description, feature, url, accent, source, start, length):
                        if page.locator('#new-button').is_visible():
                            page.locator('#new-button').click()
                        else:
                            page.locator('.first-success details > summary').click()
                            page.locator('.first-success [data-new]').click()
                        form = page.locator('#create-form')
                        for key, value in {'name': brand, 'audience': 'プロダクトの制作手順を確認する人',
                                           'tagline': tagline, 'description': description, 'features': feature,
                                           'product_url': url, 'accent': accent}.items():
                            form.locator(f'[name="{key}"]').fill(value)
                        form.locator('[name="claims_confirmed"]').check()
                        form.locator('[name="goal"]').select_option('github')
                        page.locator('#capture-mode').select_option('upload')
                        form.locator('[name="capture_start"]').fill(str(start))
                        form.locator('[name="capture_length"]').fill(str(length))
                        form.locator('details.advanced > summary').click()
                        form.locator('[name="quality"]').select_option('hd')
                        expect(form.locator('[name="review_plan"]')).to_be_checked()
                        page.locator('#capture-file').set_input_files(str(source))
                        return form

                    def play_and_download(label):
                        for ratio, shape in SHAPES.items():
                            page.locator(f'[data-ratio="{ratio}"]').click()
                            page.locator('#film-player').evaluate('(v) => v.play()')
                            page.wait_for_function('() => {const v=document.querySelector("#film-player"); return v.currentTime>.4 && v.getVideoPlaybackQuality().totalVideoFrames>0}')
                            actual = page.locator('#film-player').evaluate('(v) => [v.videoWidth,v.videoHeight]')
                            assert tuple(actual) == shape, actual
                            page.locator('#film-player').evaluate('(v) => v.pause()')
                        with page.expect_download() as download: page.locator('a[download]').click()
                        kit = output / (label + '-launch-kit.zip'); download.value.save_as(kit)
                        return kit

                    def check_cta(cid, url, label):
                        page.locator('[data-tab="site"]').click()
                        expect(page.frame_locator('.site-frame').locator('.hero a.cta')).to_be_visible()
                        expect(page.frame_locator('.site-frame').locator('.hero a.cta')).to_have_attribute('href', url)
                        page.screenshot(path=str(output / (label + '-site-preview.png')), full_page=True)
                        # Open the product's normal standalone preview, whose CTA
                        # navigation is not constrained by the editor iframe sandbox.
                        with page.expect_popup() as popup:
                            page.locator('a[target="_blank"][href*="site/index.html"]').click()
                        lp = popup.value; lp.wait_for_load_state('domcontentloaded')
                        cta = lp.locator('.hero a.cta'); expect(cta).to_be_visible(); expect(cta).to_be_enabled()
                        # A page route overrides the offline context route only for
                        # this exact read-only product destination. No mock response.
                        lp.route(url, lambda route: route.continue_() if route.request.method == 'GET' else route.abort())
                        with lp.expect_navigation(wait_until='domcontentloaded', timeout=60000) as nav: cta.click()
                        response = nav.value
                        assert response and response.status == 200 and lp.url.rstrip('/') == url, (response.status if response else None, lp.url)
                        title = lp.title()
                        assert 'GitHub' in title and url.split('github.com/')[1].lower() in title.lower(), title
                        expect(lp.locator('.markdown-body').first).to_be_visible(timeout=15000)
                        record(label + '-cta', {'visible_enabled': True, 'actual_destination': lp.url, 'http_status': response.status, 'title': title, 'analytics_tested': False})
                        lp.close()
                        page.locator('[data-tab="film"]').click(); page.locator('#result-title').wait_for()

                    scenarios = [
                        ('genie', 'Genie', '既存のGenie実演を、制作手順とともに。',
                         '既存の編集済みGenie実演です。待機・修正は短縮済み。完成版はCodex併用。現在版の自律性や速度の証明ではありません。',
                         '既存実演を確認 | 保存された画面の流れを確認できます | PRIVATE-HD-ACCEPTANCE: source hash verified',
                         GENIE_URL, '#246bce', args.source, 3, 20),
                        ('launchloom', 'Launchloom', '動画・紹介ページ・SNS原稿を、ひとつの企画から。',
                         'インストール済みLaunchloomの標準画面で、企画入力と動画の取込方法を確認した実演です。外部公開は行っていません。',
                         '企画入力と動画取込 | 制作前に入力内容を確認できます | PRIVATE-HD-ACCEPTANCE: live installed UI recording',
                         LAUNCHLOOM_URL, '#da6a45', second_source, 1, 8)]
                    saved = []
                    for label, brand, tagline, description, feature, url, accent, source, start, length in scenarios:
                        before = ids()
                        form = fill_form(brand, tagline, description, feature, url, accent, source, start, length)
                        # A rights-negative must fail before a campaign is created.
                        page.locator('#create-submit').click()
                        expect(page.locator('#create-error')).not_to_be_empty()
                        assert ids() == before
                        form.locator('[name="media_rights"]').check()
                        page.locator('#create-submit').click()
                        page.locator('#create-dialog').wait_for(state='hidden')
                        page.locator('#review-panel-title').wait_for(timeout=90000)
                        added = ids() - before; assert len(added) == 1
                        cid = added.pop(); current = snapshot(cid)
                        assert current['brief']['name'] == brand and current['brief']['product_url'] == url
                        assert current['brief']['is_sample'] is False and current['options']['quality'] == 'hd'
                        assert current['state'] == 'awaiting_review'
                        root = data / 'campaigns' / cid
                        source_hash = sha256(source)
                        assert sha256(root / 'input/capture.bin') == source_hash
                        assert not (root / 'landscape.mp4').exists()
                        title = tagline; caption = brand + 'の確認用SRT字幕。'
                        page.locator('.scene-caption').first.fill(caption)
                        page.locator('#save-plan').click()
                        expect(page.locator('#plan-save-state')).to_have_text('保存済みの内容を表示しています')
                        page.reload(); page.locator('#review-panel-title').wait_for()
                        assert page.locator('.scene-caption').first.input_value() == caption
                        stop_server(); start_server()
                        page.goto(base + '/?campaign=' + cid + '&tab=film'); page.locator('#review-panel-title').wait_for()
                        assert page.locator('.scene-caption').first.input_value() == caption
                        record(label + '-review-restart', {'campaign': cid, 'new_campaign': True, 'rights_negative': True, 'source_sha256': source_hash})
                        started = time.monotonic(); page.locator('#approve-plan').click()
                        page.locator('#result-title').wait_for(timeout=600000)
                        ready = snapshot(cid); assert ready['state'] == 'ready'
                        kit = play_and_download(label)
                        first = validate_kit(kit, output / label, cid=cid, revision=ready['revision'], brand=brand, url=url, title=title, caption=caption, seconds=length + 6)
                        page.screenshot(path=str(output / (label + '-ready.png')), full_page=True)
                        record(label + '-hd-export', {'campaign': cid, 'render_seconds': round(time.monotonic()-started, 2), **first})
                        check_cta(cid, url, label)
                        saved.append((cid, kit, ready['revision']))
                        if label == 'genie':
                            old_revision = ready['revision']; source_mtime = (root / 'input/capture.bin').stat().st_mtime_ns
                            revised_title = 'Genieの既存実演を、もう一度確認。'; revised_caption = '改訂後も、既存実演であることを明記します。'
                            page.locator('.revise-panel > summary').click()
                            page.locator('.revise-panel .scene-title').first.fill(revised_title)
                            page.locator('.revise-panel .scene-caption').first.fill(revised_caption)
                            page.locator('#revise-plan').click()
                            expect(page.locator('#result-title')).not_to_be_visible(timeout=15000)
                            page.locator('#result-title').wait_for(timeout=600000)
                            revised = snapshot(cid); assert revised['revision'] == old_revision + 1
                            revised_kit = play_and_download(label + '-revised')
                            final = validate_kit(revised_kit, output / (label + '-revised'), cid=cid, revision=old_revision + 1, brand=brand, url=url, title=revised_title, caption=revised_caption, seconds=length + 6)
                            for ratio in SHAPES: assert final['media'][ratio]['sha256'] != first['media'][ratio]['sha256']
                            assert sha256(root / 'input/capture.bin') == source_hash and (root / 'input/capture.bin').stat().st_mtime_ns == source_mtime
                            with zipfile.ZipFile(kit) as old, zipfile.ZipFile(revised_kit) as new:
                                for name in ('site/index.html', 'posts.json', 'social-copy.md'):
                                    assert old.read(name) == new.read(name), 'Standard brief-based copy unexpectedly changed'
                            record('genie-real-revision', {'revision': revised['revision'], 'both_mp4_hashes_changed': True, 'input_unchanged': True, 'lp_social_unchanged_as_documented': True, **final})
                            saved[-1] = (cid, revised_kit, revised['revision'])
                    assert len(ids()) == 2
                    stop_server(); start_server()
                    for cid, kit, revision in saved:
                        page.goto(base + '/?campaign=' + cid + '&tab=film'); page.locator('#result-title').wait_for()
                        reopened = snapshot(cid)
                        assert reopened['revision'] == revision and reopened['released'] == 0 and reopened['publications'] == []
                        downloaded = play_and_download('restart-' + cid)
                        assert downloaded.read_bytes() == kit.read_bytes()
                    with sqlite3.connect(data / 'launchloom.sqlite3') as db:
                        assert db.execute('SELECT count(*) FROM provider_runs').fetchone()[0] == 0
                        job_states = db.execute('SELECT state FROM jobs').fetchall()
                        assert len(job_states) == 5 and all(row[0] == 'complete' for row in job_states), job_states
                    assert not report['page_errors'], report['page_errors']
                    record('two-brand-final-restart', {'campaigns': len(ids()), 'complete_jobs': 5, 'byte_identical_downloads': True, 'provider_runs': 0, 'published': False})
                    browser.close(); browser = None
                except BaseException:
                    if page:
                        report['failure_url'] = page.url
                        try: page.screenshot(path=str(output / 'failure.png'), full_page=True, timeout=10000)
                        except Exception as error: report['screenshot_error'] = str(error)
                    try:
                        report['failure_campaigns'] = [
                            {key: item.get(key) for key in ('id', 'state', 'stage', 'error')}
                            for item in api.get('/api/campaigns').json()]
                    except Exception as error: report['state_error'] = str(error)
                    raise
        assert all(status == 'PASS' for status in report['required_checks'].values())
        report['status'] = 'PASS'
    except BaseException:
        report['status'] = 'FAIL'; report['failure'] = traceback.format_exc()
        if page:
            try: page.screenshot(path=str(output / 'failure.png'), full_page=True, timeout=10000)
            except Exception: pass
        raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path)
    p.add_argument('--source', type=Path)
    p.add_argument('--wheel', type=Path)
    p.add_argument('--source-sha256')
    p.add_argument('--source-provenance')
    p.add_argument('--revision')
    p.add_argument('--browser-executable')
    p.add_argument('--serve', type=Path); p.add_argument('--port', type=int)
    return p


if __name__ == '__main__':
    p = parser(); args = p.parse_args()
    if args.serve: serve(args.serve, args.port)
    else:
        for required in ('output', 'source', 'wheel', 'source_sha256', 'source_provenance', 'revision'):
            if getattr(args, required) is None: p.error('--' + required.replace('_', '-') + ' is required')
        main(args)
