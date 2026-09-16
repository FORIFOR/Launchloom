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
    assert len(p.videos) == 2 and all('controls' in v for v in p.videos)
    assert all('autoplay' not in v for v in p.videos)
    assert len(re.findall(r'<ul\b[^>]*\bclass="drafts"[^>]*>', text)) == 1
    assert len(re.findall(r'<template\b[^>]*\bdata-caption="posts"[^>]*>', text)) == 1
    assert 'Seedance専用API・エージェント自動実行</td><td>未実装' in text
    assert '実SNSアカウントでの公開は未検証' in text
