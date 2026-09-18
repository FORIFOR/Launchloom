from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def pages():
    return [(ROOT/'homepage/ja/index.html').read_text(), (ROOT/'homepage/index.html').read_text()]

def test_horio_premium_real_product_first_and_one_signature():
    for text in pages():
        assert text.count('data-signature') == 1
        assert text.count('data-actual-product') == 1
        assert 'film.mp4' in text and 'film-vertical.mp4' in text
        assert 'generated-page.png' in text and 'review-gate.png' in text
        assert 'autoplay' not in text

def test_horio_premium_avoids_ai_template_visual_cliches():
    css=(ROOT/'homepage/horio-premium.css').read_text().lower()
    for banned in ['linear-gradient','radial-gradient','backdrop-filter','blur(','glassmorphism','particle','orb']:
        assert banned not in css
    assert '#a83b2f' in css and '#171a17' in css and '#f6f5f0' in css

def test_mobile_is_not_desktop_shrink():
    css=(ROOT/'homepage/horio-premium.css').read_text()
    assert '@media(max-width:760px)' in css
    assert '.desktop-film{display:none}' in css
    assert '.mobile-film{display:block}' in css
    assert 'display:contents' in css

def test_post_sample_update_contract_is_preserved():
    for text in pages():
        assert len(re.findall(r'<ul\b[^>]*\bclass="drafts"[^>]*>',text))==1
        assert len(re.findall(r'<template\b[^>]*\bdata-caption="posts"[^>]*>',text))==1

def test_capability_copy_does_not_overclaim():
    ja,en=pages()
    assert 'Seedance 2.5・コーディングエージェント実行' in ja and '明示実行を実装' in ja
    assert '実SNSアカウントでの公開は未検証' in ja
    assert 'Seedance 2.5 + coding-agent execution' in en and 'Opt-in implementation' in en
    assert 'Real social-account publishing is unverified' in en

def test_signature_is_the_only_authored_motion():
    css=(ROOT/'homepage/horio-premium.css').read_text()
    # exactly the two declarations that make up the single aperture interaction
    assert css.count('transition:clip-path') == 1
    assert '@keyframes' not in css
