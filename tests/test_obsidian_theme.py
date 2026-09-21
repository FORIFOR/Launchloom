"""The Obsidian layer is additive: it recolours the studio without replacing
the earlier layers' sizing, hit areas or reduced-motion behaviour."""
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient

from launchloom.config import Settings
from launchloom.server import create_app

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'launchloom/web'


def test_obsidian_loads_after_the_earlier_theme_layers():
    app = (WEB / 'app.css').read_text()
    assert app.index('quiet-cinema.css') < app.index('obsidian.css')


def test_theme_keeps_the_reference_dark_tokens():
    theme = (WEB / 'obsidian.css').read_text()
    # Background, hairline border, foreground and muted foreground, read from
    # the reference implementation's published dark theme.
    for token in ('#000', '#1a1a1a', '#fafafa', '#a1a1a1'):
        assert token in theme
    assert 'color-scheme:dark' in theme


def test_theme_stays_offline_and_keeps_motion_and_focus_guarantees():
    for name in ('obsidian.css', 'obsidian-board.css'):
        theme = (WEB / name).read_text()
        assert 'https:' not in theme and '@import' not in theme, name
        assert 'prefers-reduced-motion' in theme, name
        assert ':focus-visible' in theme, name


def test_every_studio_document_declares_the_dark_ground():
    for name in ('index.html', 'production.html', 'creative-studio.html'):
        assert '<meta name="theme-color" content="#000000">' in (WEB / name).read_text(), name


def test_board_and_preview_editor_load_the_layer_after_their_own_sheet():
    for name, own in (('production.html', 'production.css'), ('creative-studio.html', 'creative-studio.css')):
        html = (WEB / name).read_text()
        assert html.index(own) < html.index('obsidian-board.css'), name


def test_preview_stage_keeps_the_rendered_film_colours():
    # The stage shows what the film will look like. Repainting it with the page
    # tokens would make the preview disagree with the actual render.
    board = (WEB / 'obsidian-board.css').read_text()
    assert '.stage{background:#F6F5F0;color:#20251F}' in board
    assert '.stage[data-preset=spotlight]{background:#171A17' in board
    assert '.stage p,.stage label{color:inherit}' in board


def test_static_mount_serves_the_layers_without_auth_bypass():
    with tempfile.TemporaryDirectory() as d:
        with TestClient(create_app(Settings(data_dir=Path(d), token='x' * 32), run_worker=False)) as client:
            for name in ('obsidian.css', 'obsidian-board.css'):
                response = client.get('/static/' + name)
                assert response.status_code == 200, name
                assert 'text/css' in response.headers['content-type']
            assert client.get('/api/campaigns').status_code == 401
