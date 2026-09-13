"""Check that every claim in the output traces back to an approved feature.

This is the promise the whole tool rests on: a film, a page or a post may only
say what the operator wrote down and approved, and the private evidence note
behind a feature never leaves the machine. `qa.json` used to report that promise
as a constant `True`, which is an assertion, not a check. This module is the
check.

It is deliberately structural. Rather than reading the copy and judging whether
it is truthful — which no automated check can do — it verifies that the copy is
composed only from text the operator approved, that every proof scene is still
bound to the approved feature it was planned against, and that no unapproved
feature or evidence note appears anywhere in the export.
"""
from __future__ import annotations
import html
import json
import re
from .models import Brief, Plan

# A very short string ("AI", "Fast") can appear inside unrelated copy by accident,
# and blocking an export over that would be worse than the leak it guards against.
# Short titles are already covered structurally: the page renders approved features
# only, and every proof scene carries the index of the feature it belongs to.
LEAK_FLOOR = 8


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def surfaces(plan: Plan, posts: list[dict], site_html: str, captions: str,
             social_copy: str = "") -> dict[str, str]:
    """Every place words reach a reader, as normalised text."""
    return {
        "storyboard": normalise(json.dumps(plan.model_dump(), ensure_ascii=False)),
        "posts": normalise(" ".join(post.get("content", "") for post in posts)),
        "social-copy.md": normalise(social_copy),
        "site/index.html": normalise(site_html),
        "captions.srt": normalise(captions),
    }


def inspect(brief: Brief, plan: Plan, posts: list[dict], site_html: str,
            captions: str, social_copy: str = "") -> list[str]:
    """Return one finding per violation. An empty list is the passing result."""
    findings: list[str] = []
    approved = [f for f in brief.features if f.approved]
    approved_indices = {i for i, f in enumerate(brief.features) if f.approved}
    seen = surfaces(plan, posts, site_html, captions, social_copy)

    # 1. Structure: a proof scene may only point at a feature that was approved.
    for position, scene in enumerate(plan.scenes):
        if scene.feature_index is None:
            continue
        if scene.feature_index not in approved_indices:
            findings.append(
                f"scene {position} is bound to feature {scene.feature_index}, which is not approved")

    # 2. Wording: a generated storyboard says exactly what the feature says. An
    #    operator-edited one may be reworded, and then only the binding holds.
    if plan.source != "operator-edited":
        for position, scene in enumerate(plan.scenes):
            if scene.kind != "proof" or scene.feature_index is None:
                continue
            if scene.feature_index in approved_indices:
                feature = brief.features[scene.feature_index]
                if normalise(scene.title) != normalise(feature.title):
                    findings.append(
                        f"scene {position} claims {scene.title!r}, which is not feature "
                        f"{scene.feature_index}'s title {feature.title!r}")

    # 3. Leakage: nothing the operator withheld may appear anywhere.
    for index, feature in enumerate(brief.features):
        if feature.approved:
            continue
        for field in ("title", "detail"):
            text = normalise(getattr(feature, field))
            if len(text) < LEAK_FLOOR:
                continue
            for where, content in seen.items():
                if text in content:
                    findings.append(
                        f"unapproved feature {index} ({field}) appears in {where}")
    for index, feature in enumerate(brief.features):
        note = normalise(feature.evidence)
        if len(note) < LEAK_FLOOR:
            continue
        for where, content in seen.items():
            if note in content:
                findings.append(f"the evidence note for feature {index} appears in {where}")

    # 4. The page shows the approved features, all of them and only them.
    rendered = re.findall(r"<h3>(.*?)</h3>", site_html, re.S)
    expected = [normalise(f.title) for f in approved]
    if [normalise(t) for t in rendered] != expected:
        findings.append(
            f"the landing page lists {[normalise(t) for t in rendered]}, "
            f"not the approved features {expected}")
    return findings
