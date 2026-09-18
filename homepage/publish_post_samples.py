"""Replace only the public draft examples with output from the real generator."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import re

DRAFTS = re.compile(r'(<ul\b[^>]*\bclass="drafts"[^>]*>).*?(</ul>)', re.S)
CAPTION = re.compile(r'(<template\b[^>]*\bdata-caption="posts"[^>]*>).*?(</template>)', re.S)
CHANNELS = {'x', 'bluesky', 'threads', 'linkedin', 'youtube', 'instagram', 'tiktok'}


def render_page(source: str, drafts: list[dict], language: str) -> str:
    if language not in {'ja', 'en'}:
        raise ValueError('Unsupported language')
    if len(drafts) != 7 or {d['channel'] for d in drafts} != CHANNELS:
        raise ValueError('Exactly seven supported channels are required')
    if any(d.get('state') != 'draft' or not d.get('content', '').strip() for d in drafts):
        raise ValueError('Only nonempty drafts may be published as examples')
    if len({d['content'] for d in drafts}) != 7:
        raise ValueError('Channel examples must not repeat the same content')
    if len(DRAFTS.findall(source)) != 1 or len(CAPTION.findall(source)) != 1:
        raise ValueError('Page structure changed; refusing an ambiguous replacement')
    items = ''.join('<li><span class="ch">' + html.escape(d['channel']) + '</span><pre>' + html.escape(d['content']) + '</pre></li>' for d in drafts)
    note = ('7媒体の投稿案を現在の生成処理で再生成。未投稿の下書きです。動画・紹介ページ・配布キットは既存の制作例で、今回再生成したものではありません。'
            if language == 'ja' else 'Seven drafts regenerated with the current generator; none have been posted. The videos, landing page and downloadable kit remain the existing production examples, not newly generated outputs.')
    result = DRAFTS.sub(lambda m: m[1] + items + m[2], source, count=1)
    return CAPTION.sub(lambda m: m[1] + html.escape(note) + m[2], result, count=1)


def publish(root: Path, samples: dict) -> list[Path]:
    root = root.resolve()
    targets = [('en', root / 'index.html'), ('ja', root / 'ja/index.html')]
    # Validate both pages before touching either. Preserve every unrelated byte.
    prepared = [(path, render_page(path.read_text(encoding='utf-8'), samples[lang], lang)) for lang, path in targets]
    manifest = {'scope': 'Only post examples regenerated; existing videos, site and kit unchanged', 'drafts': samples}
    prepared.append((root / 'post-drafts.json', json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'))
    for path, content in prepared:
        temp = path.with_name(path.name + '.post-samples.tmp')
        temp.write_text(content, encoding='utf-8')
        temp.replace(path)
    return [p for p, _ in prepared]


def main() -> None:
    from homepage.refresh_post_samples import build_samples
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site', type=Path, required=True)
    args = parser.parse_args()
    for path in publish(args.site, build_samples()):
        print('Updated', path)


if __name__ == '__main__':
    main()
