"""Claims QA: nothing reaches a reader that the operator did not approve.

Every other test here checks a behaviour. This one checks the promise — across
enough generated briefs that a leak cannot hide behind the one fixture everybody
looks at. Each brief carries deliberately withheld features and private evidence
notes, and every surface of the export is read back and searched for them.
"""
from __future__ import annotations
import random
import pytest
from launchloom.claims import inspect
from launchloom.config import Settings
from launchloom.models import Brief, Feature
from launchloom.planning import make_plan, make_posts
from launchloom.rendering import STYLES
from launchloom.site import build_site

CHANNELS = ["x", "linkedin", "threads", "bluesky", "youtube", "instagram", "tiktok"]

# Realistic copy, in both languages, plus the shapes that have historically broken
# string handling: quotes, angle brackets, ampersands, kinsoku punctuation, emoji.
TITLES = [
    "一度の入力で、全部そろう", "録画から、そのまま組み立てる", "書き出す前に、読んで直せる",
    "縦長は、切り抜きではありません", "根拠のない主張は出しません",
    "One brief, every asset", "Records your real product", "Nothing renders unread",
    'A "vertical" cut, composed separately', "Claims & evidence stay bound",
    "<script>alert(1)</script> is just text", "禁則処理つきの改行 — 、や。で始まらない",
    "Ship it 🚀 without inventing anything",
]
DETAILS = [
    "横長の映像、縦長の映像、ランディングページ、字幕、投稿原稿を一度の工程で書き出します。",
    "Playwright があなたのアプリを操作し、その画面を証拠として収録します。",
    "収録が終わった時点で制作が止まるので、すべての文言を読んでから承認できます。",
    "A landscape film, a vertical cut, a landing page, captions and post drafts, written in one pass.",
    "The build stops after capture so every scene can be reworded before anything renders.",
    'Angle brackets <b>, ampersands & quotes " stay exactly as typed.',
]
EVIDENCE = [
    "社内Wikiの機能一覧 2026-08 版、行32。公開不可。",
    "Internal spec §4.2, not for publication — reviewed by the platform team on 2026-07-14.",
    "顧客Aとの議事録（NDA対象）。この文言は絶対に外に出さないこと。",
]


def a_brief(seed: int) -> Brief:
    """One deterministic brief, with real approvals and real withheld features."""
    rng = random.Random(seed)
    count = rng.randint(1, 8)
    features = []
    for i in range(count):
        # Withheld features get a marker so a leak is identifiable, appended to
        # realistic copy so the test is not just searching for a sentinel.
        approved = i == 0 or rng.random() < 0.55
        title = rng.choice(TITLES)
        detail = rng.choice(DETAILS)
        if not approved:
            title = f"{title}（未承認{seed}_{i}）"[:60]
            detail = f"{detail} WITHHELD-{seed}-{i}"[:180]
        features.append(Feature(title=title, detail=detail,
                                evidence=f"{rng.choice(EVIDENCE)} ref={seed}-{i}" if approved
                                         or rng.random() < 0.5 else "",
                                approved=approved))
    return Brief(
        name=rng.choice(["Launchloom", "Orbit", "Cadence", "帆布", "Nine & Co."]),
        tagline=rng.choice(TITLES)[:90],
        audience=rng.choice(["ひとりで作って、ひとりで届ける人へ", "Developers who ship alone",
                             "小さなチームの開発者", "Founders & indie makers"]),
        description=rng.choice(DETAILS),
        product_url=rng.choice(["", "https://example.com/app", "https://example.com/a?b=1"]),
        features=features,
        language=rng.choice(["ja", "en"]),
        goal=rng.choice(["signups", "demos", "github"]),
        channels=rng.sample(CHANNELS, rng.randint(1, len(CHANNELS))),
    )


CASES = [a_brief(seed) for seed in range(300)]


@pytest.mark.parametrize("brief", CASES, ids=[f"brief{i}" for i in range(len(CASES))])
def test_no_claim_escapes_the_brief(brief, tmp_path):
    style = list(STYLES)[hash(brief.name) % len(STYLES)]
    plan = make_plan(brief, style)
    posts = make_posts(brief, "0123456789abcdef")
    settings = Settings(data_dir=tmp_path / "data", token="test-local-token-with-32-characters")
    build_site(brief, "0123456789abcdef", tmp_path / "site", settings, has_film=True)
    site_html = (tmp_path / "site" / "index.html").read_text()
    captions = "\n".join(scene.caption or scene.title for scene in plan.scenes)
    social = "\n".join(post["content"] for post in posts)
    assert inspect(brief, plan, posts, site_html, captions, social) == []


def test_the_corpus_actually_withholds_things():
    """A test that never sees an unapproved feature proves nothing."""
    withheld = sum(1 for b in CASES for f in b.features if not f.approved)
    notes = sum(1 for b in CASES for f in b.features if f.evidence)
    assert withheld > 300, withheld
    assert notes > 300, notes
    assert {b.language for b in CASES} == {"ja", "en"}
    assert max(len(b.features) for b in CASES) == 8


def test_a_leaked_feature_is_caught():
    """The checker has to be able to fail, or the 300 passes above mean nothing."""
    brief = a_brief(1)
    plan = make_plan(brief)
    posts = make_posts(brief, "0123456789abcdef")
    withheld = next(f for f in brief.features if not f.approved)
    leaked = [dict(posts[0], content=posts[0]["content"] + "\n" + withheld.detail)] + posts[1:]
    findings = inspect(brief, plan, leaked, "<h3>" + brief.features[0].title + "</h3>", "", "")
    assert any("unapproved feature" in f for f in findings), findings


def test_a_leaked_evidence_note_is_caught():
    brief = a_brief(2)
    plan = make_plan(brief)
    note = next(f.evidence for f in brief.features if f.evidence)
    html = "<h3>" + "</h3><h3>".join(f.title for f in brief.features if f.approved) + "</h3>"
    findings = inspect(brief, plan, [], html, note, "")
    assert any("evidence note" in f for f in findings), findings


def test_a_scene_rebound_to_an_unapproved_feature_is_caught():
    brief = a_brief(3)
    plan = make_plan(brief)
    unapproved = next(i for i, f in enumerate(brief.features) if not f.approved)
    proof = next(s for s in plan.scenes if s.kind == "proof")
    proof.feature_index = unapproved
    html = "<h3>" + "</h3><h3>".join(f.title for f in brief.features if f.approved) + "</h3>"
    findings = inspect(brief, plan, [], html, "", "")
    assert any("not approved" in f for f in findings), findings
