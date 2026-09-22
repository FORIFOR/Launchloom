from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_studio_loads_quiet_cinema_last():
    app = (ROOT / 'launchloom/web/app.css').read_text()
    assert app.index("workspace.css") < app.index("quiet-cinema.css")
    theme = (ROOT / 'launchloom/web/quiet-cinema.css').read_text()
    for token in ('#F6F5F0', '#20251F', '#171A17', '#A83B2F'):
        assert token in theme
    assert '.player' in theme and '.post-grid' in theme


def test_production_board_uses_editorial_roles():
    html = (ROOT / 'launchloom/web/production.html').read_text()
    js = (ROOT / 'launchloom/web/production.js').read_text()
    assert 'PRODUCTION / SHOT LIST' in html
    assert 'scene-role' in html
    assert 'PRODUCT / 実際の動作' in js
    assert 'ATMOSPHERE / 雰囲気' in js
    assert 'MOTION / 文字と演出' in js


def test_quiet_cinema_documented():
    doc = (ROOT / 'docs/QUIET_CINEMA.md').read_text()
    assert 'The product is the image' in doc
    assert 'No fake evidence' in doc


def test_public_homepages_use_quiet_cinema_without_claiming_new_capabilities():
    ja = (ROOT / 'homepage/ja/index.html').read_text()
    en = (ROOT / 'homepage/index.html').read_text()
    # Public pages now share a dedicated stylesheet instead of duplicating the
    # palette inside each HTML document. Keep the theme contract, but do not
    # force presentation tokens to be inline.
    theme = (ROOT / 'homepage/horio-premium.css').read_text()
    for token in ('#A83B2F', '#171A17', '#F6F5F0'):
        assert token in theme
    assert 'href="../horio-premium.css"' in ja
    assert 'href="./horio-premium.css"' in en
    # The headline used to be a mood line ("作ったものを、届けられる形へ。" /
    # "Built to be seen."). Measured against five current reference pages, the
    # first-line practice is to spend the largest type on what the product does,
    # so the assertion now demands that rather than pinning one phrase: the h1
    # has to name the deliverables a stranger would be looking for.
    import re as _re
    for text, words in ((ja, ('動画', '紹介ページ', '投稿文')), (en, ('film', 'page', 'posts'))):
        h1 = _re.search(r'<h1>(.*?)</h1>', text, _re.S)
        assert h1, 'the page has no h1'
        head = h1.group(1).replace('<br>', ' ')
        for w in words:
            assert w in head, (w, head)
    # Capability labels remain explicit after the visual redesign.
    assert 'Seedance 2.5・コーディングエージェント実行' in ja
    assert '明示実行を実装' in ja
