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
    assert '作ったものを、<br>届けられる形へ。' in ja
    assert 'Built to be<br>seen.' in en
    # Capability labels remain explicit after the visual redesign.
    assert 'Seedance専用API・エージェント自動実行' in ja
    assert '未実装' in ja
