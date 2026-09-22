from pathlib import Path
from html.parser import HTMLParser
import re


class Tags(HTMLParser):
    def __init__(self):
        super().__init__(); self.ids = []; self.hashes = []; self.videos = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if 'id' in a: self.ids.append(a['id'])
        if tag == 'a' and a.get('href', '').startswith('#'): self.hashes.append(a['href'][1:])
        if tag == 'video': self.videos.append(a)


def test_homepage_keeps_samples_and_accessible_navigation():
    text = (Path(__file__).resolve().parents[1] / 'homepage/ja/index.html').read_text()
    p = Tags(); p.feed(text)
    assert len(p.ids) == len(set(p.ids))
    assert set(p.hashes) <= set(p.ids)
    # Videos come in desktop/mobile pairs, so the mobile view is a re-cut and
    # not a shrunken desktop frame. Count the pairs rather than the elements:
    # the page may carry more than one pair (the studio recording and the film
    # a run produced), but each must still be a complete pair.
    assert p.videos, 'the page shows no video at all'
    assert len(p.videos) % 2 == 0, p.videos
    desktop = [v for v in p.videos if v.get('class') == 'desktop-film']
    mobile = [v for v in p.videos if v.get('class') == 'mobile-film']
    assert len(desktop) == len(mobile) == len(p.videos) // 2, p.videos
    assert all('controls' in v for v in p.videos)
    assert all('autoplay' not in v for v in p.videos)
    assert all(v.get('poster') for v in p.videos), 'every video needs a poster'
    assert len(re.findall(r'<ul\b[^>]*\bclass="drafts"[^>]*>', text)) == 1
    assert len(re.findall(r'<template\b[^>]*\bdata-caption="posts"[^>]*>', text)) == 1
    assert 'Seedance 2.5・コーディングエージェント実行' in text and '明示実行を実装' in text
    assert '実SNSアカウントでの公開は未検証' in text


def test_final_film_workflow_and_samples_are_discoverable_in_both_languages():
    root=Path(__file__).resolve().parents[1]/'homepage'
    ja=(root/'ja/index.html').read_text()
    en=(root/'index.html').read_text()
    assert '完成動画の取り込み→投稿準備' in ja
    assert 'href="launch-kit.zip"' in ja
    assert 'production-sample.zip' in ja and 'production-sample.zip' in en
    assert 'Execution boundary:' in en and 'explicit opt-in actions' in en
    assert 'no account, no API key, nothing leaves your machine' not in en
    import zipfile
    with zipfile.ZipFile(root/'production-sample.zip') as z:
        assert z.testzip() is None
        assert 'build.jsx' in z.namelist()
        assert 'NOT a completed video' in z.read('README.md').decode()
