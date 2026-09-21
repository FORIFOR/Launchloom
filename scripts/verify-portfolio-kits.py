"""Decode every exported movie and verify local assets; does not certify visual taste."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs
from array import array
import hashlib
import json
import math
import subprocess
import sys


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('src', 'poster') and value and not urlparse(value).scheme:
                self.paths.append(value)


def samples(path, start):
    raw = subprocess.check_output(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(start),
        '-i', str(path), '-t', '10', '-vn', '-ar', '8000', '-ac', '1', '-f', 'f32le', '-'])
    values = array('f')
    values.frombytes(raw)
    return values


def correlation(left, right):
    n = min(len(left), len(right))
    if not n:
        return None
    x, y = left[:n], right[:n]
    mx, my = sum(x)/n, sum(y)/n
    a = sum((v-mx)**2 for v in x)
    b = sum((v-my)**2 for v in y)
    return sum((v-mx)*(w-my) for v, w in zip(x, y))/math.sqrt(a*b) if a*b else None


def main():
    root = Path(sys.argv[1]).resolve()
    projects = Path(sys.argv[2]).resolve() if len(sys.argv)>2 else Path(__file__).resolve().parents[2]
    source = json.loads((root/'portfolio-evidence.json').read_text())
    rows = []
    for folder, product in zip(['genie', 'ai-meeting', 'oathra', 'aisecure', 'agent-team'], source['products']):
        directory = root/folder
        for aspect in ('landscape', 'portrait'):
            video = directory/f'{aspect}.mp4'
            metadata = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]))
            stream = next(s for s in metadata['streams'] if s['codec_type']=='video')
            dims = (1920, 1080) if aspect=='landscape' else (1080, 1920)
            assert (stream['width'], stream['height'])==dims
            assert stream['avg_frame_rate']=='30/1'
            subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-nostdin', '-i', str(video), '-f', 'null', '-'], check=True)
            audio = any(s['codec_type']=='audio' for s in metadata['streams'])
            assert audio==product['sourceAudioPreserved']
            corr = None
            if audio:
                corr = correlation(samples(projects/product['sourceRecording'], 0), samples(video, 3))
                assert corr is not None and corr>0.95, (video, corr)
            rows.append({'product': product['product'], 'aspect': aspect, 'sha256': hashlib.sha256(video.read_bytes()).hexdigest(),
                'width': dims[0], 'height': dims[1], 'fps': 30, 'durationSeconds': float(metadata['format']['duration']),
                'fullDecode': True, 'audio': audio, 'sourceAudioCorrelationAt3SecondOffset': corr})
        parser = Assets()
        parser.feed((directory/'site/index.html').read_text())
        for path in parser.paths:
            assert (directory/'site'/path).is_file(), path
        posts = json.loads((directory/'posts.json').read_text())
        assert len(posts)==4 and {p['channel'] for p in posts}=={'x','linkedin','youtube','instagram'}
        for post in posts:
            assert post['state']=='draft' and (directory/post['media']).is_file()
            query = parse_qs(urlparse(post['utm_url']).query)
            assert query['utm_source']==[post['channel']] and query['utm_medium']==['social']
            assert query['utm_campaign'] and query['utm_content']
    assert len(rows)==10
    report = {'scope':'full decode, dimensions/fps, local assets and draft metadata; audio correlation covers first ten source seconds only',
        'videos': rows, 'videoCount':10, 'landingPages':5, 'socialDrafts':20, 'passed':True,
        'notMeasured':['artistic quality','virality','whole-track subjective audio sync','mobile device readability','Safari/Firefox','Lighthouse/LCP/CLS']}
    (root/'media-validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'videos':10, 'landingPages':5, 'socialDrafts':20, 'passed':True}))


if __name__=='__main__':
    main()
