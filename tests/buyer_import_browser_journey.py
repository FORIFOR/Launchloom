"""Standard-studio import journey, called by first_success_browser_journey.

Uses only generated test footage, the disposable local server and its existing
authenticated browser. The save failure is an explicitly injected HTTP 503;
media validation, persistence, restart, rendering and downloads are real.
"""
from __future__ import annotations

import hashlib
from importlib.resources import files
import json
from pathlib import Path
import signal
import os
import sqlite3
import subprocess
import time
import traceback
import zipfile

from playwright.sync_api import expect


def run_import_journey(page, api, data, output, start_server, process, record):
    """Exercise the buyer's own-video flow and return the live server process.

    The caller owns the supplied process and its successful replacement. If this
    journey fails after restarting, clean up the replacement here so the caller
    cannot leak a server by retaining its old process reference.
    """
    original_process = process
    data, output = Path(data), Path(output)
    base = str(api.base_url).rstrip('/')
    private_evidence = 'PRIVATE-IMPORT-QA-EVIDENCE-NOT-FOR-EXPORT'
    create_keys = []
    writes = []
    cid = None
    phase = 'fixture-and-dismissal'

    def observe_request(request):
        if request.method in {'POST', 'PATCH', 'DELETE'}:
            writes.append((request.method, request.url))
        if request.method == 'POST' and request.url == base + '/api/campaigns':
            create_keys.append(request.headers.get('idempotency-key'))

    def snapshot(cid):
        response = api.get('/api/campaigns/' + cid)
        response.raise_for_status()
        return response.json()

    def campaign_ids():
        response = api.get('/api/campaigns')
        response.raise_for_status()
        return {item['id'] for item in response.json()}

    def jobs(cid):
        with sqlite3.connect(data / 'launchloom.sqlite3') as db:
            return db.execute('SELECT id,state FROM jobs WHERE campaign_id=? ORDER BY created', (cid,)).fetchall()

    def completed_jobs(cid, count):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            rows = jobs(cid)
            if len(rows) == count and all(state == 'complete' for _, state in rows):
                return rows
            time.sleep(.1)
        raise AssertionError(('Expected completed jobs', count, rows))

    def edited_values():
        return {key: page.locator(selector).first.input_value() for key, selector in (
            ('title', '.scene-title'), ('detail', '.scene-detail'), ('caption', '.scene-caption'))}

    page.on('request', observe_request)
    try:
        if page.evaluate('document.documentElement.lang') != 'ja':
            page.locator('#language-toggle').click()
            page.wait_for_function("() => document.documentElement.lang === 'ja'")
        before = campaign_ids()
        fixture = data / 'buyer-generated-testsrc.mp4'
        generated = subprocess.run([
            'ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
            'testsrc2=size=640x360:rate=30', '-t', '8', '-an',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(fixture),
        ], capture_output=True, text=True, timeout=45)
        assert generated.returncode == 0, generated.stderr
        invalid = data / 'buyer-invalid.mp4'
        invalid.write_bytes(b'This is not video. Disposable local QA fixture only.')

        # Dismissal before submission must not create a campaign or issue writes.
        writes_before = len(writes)
        page.locator('#new-button').click()
        page.locator('#create-dialog[open]').wait_for()
        page.keyboard.press('Escape')
        expect(page.locator('#create-dialog')).not_to_be_visible()
        expect(page.locator('#new-button')).to_be_focused()
        page.locator('#new-button').click()
        page.locator('[data-close="create-dialog"]').click()
        expect(page.locator('#create-dialog')).not_to_be_visible()
        assert campaign_ids() == before and len(writes) == writes_before

        page.locator('#new-button').click()
        form = page.locator('#create-form')
        phase = 'create-and-invalid-media'
        form.locator('[name="name"]').fill('Synthetic import QA')
        form.locator('[name="audience"]').fill('この試験を確認する人')
        form.locator('[name="tagline"]').fill('自作のテスト映像を確認する。')
        form.locator('[name="description"]').fill('FFmpegで作成した色と動きのテスト素材です。実在サービスの操作映像ではありません。')
        form.locator('[name="features"]').fill(
            'テストパターン | 色と動きを含む8秒の試験用映像です | ' + private_evidence)
        form.locator('[name="claims_confirmed"]').check()
        page.locator('#capture-mode').select_option('upload')
        form.locator('[name="capture_start"]').fill('1')
        form.locator('[name="capture_length"]').fill('4')
        expect(form.locator('[name="review_plan"]')).to_be_checked()
        form.locator('details.advanced > summary').click()
        form.locator('[name="quality"]').select_option('draft')
        page.locator('#capture-file').set_input_files(str(invalid))

        # Client rights validation happens before campaign creation.
        page.locator('#create-submit').click()
        expect(page.locator('#create-error')).to_contain_text('権利')
        expect(page.locator('#create-submit')).to_be_enabled()
        assert campaign_ids() == before and create_keys == []
        form.locator('[name="media_rights"]').check()

        # Repeated invalid submission must reuse the same draft and key. This is
        # real ffprobe rejection, not a mocked upload endpoint.
        for attempt in range(2):
            with page.expect_response(lambda r: '/media?kind=capture&' in r.url and r.request.method == 'POST') as upload:
                page.locator('#create-submit').click()
            assert upload.value.status == 422
            expect(page.locator('#create-error')).not_to_have_text('')
            expect(page.locator('#create-submit')).to_be_enabled()
            created = campaign_ids() - before
            assert len(created) == 1
            current = created.pop()
            if cid is not None:
                assert current == cid
            cid = current
            assert snapshot(cid)['state'] == 'draft' and jobs(cid) == []
            assert not (data / 'campaigns' / cid / 'input' / 'capture.bin').exists()
            assert not list((data / 'campaigns' / cid / 'input').glob('*.part'))
        page.screenshot(path=str(output / 'buyer-invalid-media.png'), full_page=True)

        page.locator('#capture-file').set_input_files(str(fixture))
        page.locator('#create-submit').click()
        page.locator('#create-dialog').wait_for(state='hidden')
        page.locator('#review-panel-title').wait_for(timeout=90000)
        review = snapshot(cid)
        root = data / 'campaigns' / cid
        assert campaign_ids() == before | {cid}
        assert len(create_keys) == 3 and create_keys[0] and len(set(create_keys)) == 1
        assert review['state'] == 'awaiting_review' and not review['plan_approved']
        assert review['brief']['is_sample'] is False
        assert review['options']['capture_mode'] == 'upload'
        assert review['options']['quality'] == 'draft'
        assert review['options']['review_plan'] is True
        assert review['options']['capture_start'] == 1 and review['options']['capture_length'] == 4
        assert (root / 'input' / 'capture.bin').read_bytes() == fixture.read_bytes()
        assert not (root / 'landscape.mp4').exists() and not (root / 'launch-kit.zip').exists()
        completed_jobs(cid, 1)
        page.locator('.review-still').wait_for()
        page.wait_for_function("() => document.querySelector('.review-still').naturalWidth > 0")
        record('B1-import', {'campaign': cid, 'invalid_uploads': 2, 'drafts_created': 1,
                            'same_creation_key': True, 'source': 'FFmpeg testsrc2, 8 seconds, no audio',
                            'rights_gate': 'blocked before creation', 'state': review['state']})

        phase = 'edit-and-save-recovery'
        edited = {'title': '購入者テストの見出し',
                  'detail': '購入者テストの補足を保存しました。',
                  'caption': 'この字幕は、書き出したSRTに残ります。'}
        page.locator('.scene-title').first.fill(edited['title'])
        page.locator('.scene-caption').first.fill(edited['caption'])
        page.locator('.scene-more > summary').first.click()
        page.locator('.scene-detail').first.fill(edited['detail'])
        expect(page.locator('#plan-save-state')).to_have_text('未保存の変更があります')
        plan_url = base + '/api/campaigns/' + cid + '/plan'

        def fail_save(route):
            if route.request.method == 'PATCH':
                route.fulfill(status=503, content_type='application/json',
                              body=json.dumps({'detail': 'Injected save failure; retry the same edit.'}))
            else:
                route.continue_()

        page.route(plan_url, fail_save)
        try:
            page.locator('#save-plan').click()
            expect(page.locator('#review-panel-error')).to_contain_text('Injected save failure')
            expect(page.locator('#save-plan')).to_be_enabled()
            expect(page.locator('#approve-plan')).to_be_enabled()
            expect(page.locator('.scene-caption').first).to_be_enabled()
            assert edited_values() == edited
            expect(page.locator('#plan-save-state')).to_have_text('未保存の変更があります')
            assert snapshot(cid)['plan'] == review['plan']
            page.screenshot(path=str(output / 'buyer-save-failure.png'), full_page=True)
        finally:
            page.unroute(plan_url, fail_save)

        page.locator('#save-plan').click()
        expect(page.locator('#plan-save-state')).to_have_text('保存済みの内容を表示しています')
        assert {key: snapshot(cid)['plan']['scenes'][0][key] for key in edited} == edited
        # Saving twice with no newer edits must not enqueue work.
        page.locator('#save-plan').click()
        expect(page.locator('#save-plan')).to_be_enabled()
        page.reload()
        page.locator('#review-panel-title').wait_for()
        assert edited_values() == edited and len(jobs(cid)) == 1
        page.screenshot(path=str(output / 'buyer-saved-review.png'), full_page=True)
        record('B2-save', 'Injected HTTP 503 retains all three unsaved edits; retry, repeated save and reload preserve title/detail/SRT with no new job')

        # Restart the real idle server at the review gate, distinct from R3's
        # interrupted render exercise. Explicit reads must reopen the same draft.
        phase = 'review-server-restart'
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        process = start_server()
        page.goto(base + '/?campaign=' + cid + '&tab=film')
        page.locator('#review-panel-title').wait_for()
        assert snapshot(cid)['state'] == 'awaiting_review'
        assert edited_values() == edited and campaign_ids() == before | {cid}
        assert len(jobs(cid)) == 1
        record('B3-restart', 'Real server stop/restart at review preserves imported draft, saved edits, campaign URL and one completed planning job')

        phase = 'render-and-export'
        page.locator('#approve-plan').click()
        page.locator('#result-title').wait_for(timeout=180000)
        ready = snapshot(cid)
        assert ready['state'] == 'ready' and ready['released'] == 0 and ready['publications'] == []
        completed_jobs(cid, 2)
        for ratio in ('landscape', 'portrait'):
            page.locator('[data-ratio="' + ratio + '"]').click()
            page.locator('#film-player').evaluate('(video) => video.play()')
            page.wait_for_function("() => document.querySelector('#film-player').currentTime > .4 && document.querySelector('#film-player').getVideoPlaybackQuality().totalVideoFrames > 0")
            page.locator('#film-player').evaluate('(video) => video.pause()')
        with page.expect_download() as download:
            page.locator('a[download]').click()
        kit = output / 'buyer-import-launch-kit.zip'
        download.value.save_as(kit)
        with zipfile.ZipFile(kit) as archive:
            assert archive.testzip() is None
            names = set(archive.namelist())
            required = {'landscape.mp4', 'portrait.mp4', 'captions.srt', 'storyboard.json',
                        'campaign.json', 'posts.json', 'social-copy.md', 'site/index.html',
                        'site/site.css', 'site/site.js', 'LICENSE', 'NOTICE', 'site/LICENSE', 'site/NOTICE'}
            assert required <= names
            manifest = json.loads(archive.read('manifest.json'))
            assert set(manifest['files']) == names - {'manifest.json'}
            for name, entry in manifest['files'].items():
                content = archive.read(name)
                assert hashlib.sha256(content).hexdigest() == entry['sha256'], name
                assert len(content) == entry['bytes'], name
                assert private_evidence.encode() not in content, name
            assert not any(name.startswith(('input/', 'capture/')) or name in {'brief.json', 'access-token'} for name in names)
            exported = json.loads(archive.read('storyboard.json'))['scenes'][0]
            assert {key: exported[key] for key in edited} == edited
            assert edited['caption'] in archive.read('captions.srt').decode()
            # The installed package, rather than a checkout-relative LICENSE,
            # is the authority for these exact template notices.
            for notice in ('LICENSE', 'NOTICE'):
                expected = files('launchloom').joinpath('licenses', notice).read_bytes()
                assert archive.read(notice) == archive.read('site/' + notice) == expected
            notice_text = archive.read('NOTICE').decode()
            assert 'does not relicense or clear rights to customer copy' in notice_text
            assert 'not the entire generated launch kit' in notice_text
            assert 'Generated from Launchloom template code' in archive.read('site/index.html').decode()
            for ratio, shape in (('landscape', (960, 540)), ('portrait', (540, 960))):
                film = data / ('buyer-' + ratio + '.mp4')
                film.write_bytes(archive.read(ratio + '.mp4'))
                decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(film), '-f', 'null', '-'],
                                         capture_output=True, text=True, timeout=60)
                assert decoded.returncode == 0, decoded.stderr
                probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                        '-of', 'json', str(film)], capture_output=True, text=True, timeout=15)
                assert probe.returncode == 0, probe.stderr
                metadata = json.loads(probe.stdout)
                video = next(stream for stream in metadata['streams'] if stream['codec_type'] == 'video')
                assert (video['width'], video['height']) == shape
                assert video['codec_name'] == 'h264'
                assert not any(stream['codec_type'] == 'audio' for stream in metadata['streams'])
                assert abs(float(metadata['format']['duration']) - 10) < .15
                assert (manifest['videos'][ratio]['width'], manifest['videos'][ratio]['height']) == shape
                frame = subprocess.run([
                    'ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', str(film),
                    '-frames:v', '1', str(output / ('buyer-' + ratio + '-headline.png')),
                ], capture_output=True, text=True, timeout=20)
                assert frame.returncode == 0, frame.stderr
        layout = page.evaluate("() => ({viewport:innerWidth, document:document.documentElement.scrollWidth, details:[...document.querySelectorAll('.detail-card')].map(e=>({client:e.clientWidth, scroll:e.scrollWidth}))})")
        assert layout['document'] <= layout['viewport'] + 1, layout
        page.screenshot(path=str(output / 'buyer-import-ready.png'), full_page=True)
        record('B4-export', {'kit': str(kit), 'sha256': hashlib.sha256(kit.read_bytes()).hexdigest(),
                             'members': len(names), 'both_browser_played': True,
                             'both_ffmpeg_decoded': True, 'trimmed_duration_seconds': 10,
                             'package_license_bytes_match': True, 'private_evidence_excluded': True, 'layout': layout})

        # Reopening a finished campaign and dismissing creation again must be
        # read-only and keep both the finished artifact and job history intact.
        phase = 'ready-reopen-and-dismissal'
        saved_jobs = jobs(cid)
        writes_before = len(writes)
        page.reload()
        page.locator('#result-title').wait_for()
        page.locator('#new-button').click()
        page.keyboard.press('Escape')
        expect(page.locator('#new-button')).to_be_focused()
        page.locator('#new-button').click()
        page.locator('[data-close="create-dialog"]').click()
        assert len(writes) == writes_before
        assert campaign_ids() == before | {cid} and jobs(cid) == saved_jobs
        assert 'campaign=' + cid in page.url
        assert snapshot(cid)['state'] == 'ready'
        assert hashlib.sha256((root / 'launch-kit.zip').read_bytes()).hexdigest() == hashlib.sha256(kit.read_bytes()).hexdigest()
        record('B5-reopen', 'Ready reload, Escape and Close are read-only; one imported campaign, exactly two completed jobs, same kit bytes')

        # A real second render uses the ready-campaign revision control. Hold
        # only its HTTP request until both native clicks finish, making the
        # busy-button check deterministic without dispatching synthetic events.
        phase = 'ready-revise-double-click'
        imported = root / 'input' / 'capture.bin'
        input_sha = hashlib.sha256(imported.read_bytes()).hexdigest()
        input_mtime = imported.stat().st_mtime_ns
        prior_revision = snapshot(cid)['revision']
        prior_video_hashes = {ratio: manifest['files'][ratio + '.mp4']['sha256']
                              for ratio in ('landscape', 'portrait')}
        with sqlite3.connect(data / 'launchloom.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM provider_runs').fetchone()[0] == 0
        revised_title = '購入者テストの改訂見出し'
        revised_caption = '作り直した字幕も、新しいSRTに残ります。'
        page.locator('.revise-panel > summary').click()
        page.locator('.revise-panel .scene-title').first.fill(revised_title)
        page.locator('.revise-panel .scene-caption').first.fill(revised_caption)
        revise_url = base + '/api/campaigns/' + cid + '/revise'
        held = []

        def hold_revision(route):
            held.append(route)

        writes_before = len(writes)
        page.route(revise_url, hold_revision)
        try:
            with page.expect_response(lambda response: response.url == revise_url and response.request.method == 'POST') as revision_response:
                with page.expect_request(lambda request: request.url == revise_url and request.method == 'POST'):
                    page.locator('#revise-plan').dblclick(delay=50)
                expect(page.locator('#revise-plan')).to_be_disabled()
                assert len(held) == 1, 'A double click must produce only one revision request'
                assert writes[writes_before:] == [('POST', revise_url)]
                held.pop().continue_()
            assert revision_response.value.status == 202
        finally:
            for route in held:
                route.abort()
            page.unroute(revise_url, hold_revision)
        # Waiting for the old result to leave first avoids falsely accepting the
        # previous ready screen before the asynchronous revision refresh.
        expect(page.locator('#result-title')).not_to_be_visible(timeout=15000)
        page.locator('#result-title').wait_for(timeout=180000)
        revised = snapshot(cid)
        assert revised['state'] == 'ready' and revised['revision'] == prior_revision + 1
        assert revised['released'] == 0 and revised['publications'] == []
        assert revised['options'] == ready['options']
        assert revised['plan']['scenes'][0]['title'] == revised_title
        assert revised['plan']['scenes'][0]['caption'] == revised_caption
        assert revised['plan']['scenes'][0]['detail'] == edited['detail']
        completed_jobs(cid, 3)
        assert campaign_ids() == before | {cid}
        assert hashlib.sha256(imported.read_bytes()).hexdigest() == input_sha
        assert imported.stat().st_mtime_ns == input_mtime
        assert not (root / 'capture').exists()
        assert writes[writes_before:] == [('POST', revise_url)]
        with sqlite3.connect(data / 'launchloom.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM provider_runs').fetchone()[0] == 0
        for ratio in ('landscape', 'portrait'):
            page.locator('[data-ratio="' + ratio + '"]').click()
            page.locator('#film-player').evaluate('(video) => video.play()')
            page.wait_for_function("() => document.querySelector('#film-player').currentTime > .4 && document.querySelector('#film-player').getVideoPlaybackQuality().totalVideoFrames > 0")
            page.locator('#film-player').evaluate('(video) => video.pause()')
        with page.expect_download() as download:
            page.locator('a[download]').click()
        revised_kit = output / 'buyer-import-revised-launch-kit.zip'
        download.value.save_as(revised_kit)
        assert revised_kit.read_bytes() != kit.read_bytes()
        assert revised_kit.read_bytes() == (root / 'launch-kit.zip').read_bytes()
        with zipfile.ZipFile(revised_kit) as archive:
            assert archive.testzip() is None and set(archive.namelist()) == names
            revised_manifest = json.loads(archive.read('manifest.json'))
            assert revised_manifest['campaign_id'] == cid
            assert revised_manifest['revision'] == prior_revision + 1
            assert set(revised_manifest['files']) == names - {'manifest.json'}
            for name, entry in revised_manifest['files'].items():
                content = archive.read(name)
                assert hashlib.sha256(content).hexdigest() == entry['sha256'], name
                assert len(content) == entry['bytes'], name
                assert private_evidence.encode() not in content, name
            scene = json.loads(archive.read('storyboard.json'))['scenes'][0]
            assert scene['title'] == revised_title and scene['caption'] == revised_caption
            assert scene['detail'] == edited['detail']
            subtitles = archive.read('captions.srt').decode()
            assert revised_caption in subtitles and edited['caption'] not in subtitles
            for notice in ('LICENSE', 'NOTICE'):
                expected = files('launchloom').joinpath('licenses', notice).read_bytes()
                assert archive.read(notice) == archive.read('site/' + notice) == expected
            assert 'Generated from Launchloom template code' in archive.read('site/index.html').decode()
            for ratio in ('landscape', 'portrait'):
                assert revised_manifest['files'][ratio + '.mp4']['sha256'] != prior_video_hashes[ratio]
                film = data / ('buyer-revised-' + ratio + '.mp4')
                film.write_bytes(archive.read(ratio + '.mp4'))
                decoded = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(film), '-f', 'null', '-'],
                                         capture_output=True, text=True, timeout=60)
                assert decoded.returncode == 0, decoded.stderr
                frame = subprocess.run([
                    'ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', str(film),
                    '-frames:v', '1', str(output / ('buyer-revised-' + ratio + '-headline.png')),
                ], capture_output=True, text=True, timeout=20)
                assert frame.returncode == 0, frame.stderr
        page.screenshot(path=str(output / 'buyer-import-revised-ready.png'), full_page=True)
        record('B6-revise', {'kit': str(revised_kit), 'sha256': hashlib.sha256(revised_kit.read_bytes()).hexdigest(),
                            'campaign': cid, 'revision': revised['revision'], 'completed_jobs': 3,
                            'double_click': 'Native control double-click with request held; exactly one POST and one new job',
                            'input_sha256_unchanged': input_sha, 'input_mtime_unchanged': True,
                            'both_mp4_hashes_changed': True, 'both_browser_played': True,
                            'both_ffmpeg_decoded': True, 'all_manifest_hashes_match': True,
                            'package_license_bytes_match': True, 'new_srt_verified': True,
                            'recapture': 'No capture directory or upload; source bytes and mtime unchanged',
                            'provider_runs': 0})
        return process
    except BaseException:
        failure = {'phase': phase, 'campaign': cid, 'traceback': traceback.format_exc()}
        try:
            failure['url'] = page.url
            screenshot = output / 'buyer-failure.png'
            page.screenshot(path=str(screenshot), full_page=True, timeout=10000)
            failure['screenshot'] = str(screenshot)
        except Exception as evidence_error:
            failure['screenshot_error'] = str(evidence_error)
        try:
            (output / 'buyer-failure.json').write_text(json.dumps(failure, ensure_ascii=False, indent=2))
            record('B-failure', failure, 'FAIL')
        except Exception:
            pass  # Never mask the failing product assertion with reporting.
        if process is not original_process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
        raise
    finally:
        page.remove_listener('request', observe_request)
