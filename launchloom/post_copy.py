"""Channel-specific drafts using approved public wording, never evidence notes.

Draft structure does not guarantee engagement or acceptance by a social platform.
"""
from __future__ import annotations
from collections.abc import Callable, Sequence


def compose_post_copy(*, name: str, tagline: str, audience: str,
                      features: Sequence[tuple[str, str]], channel: str,
                      language: str) -> str:
    if not features:
        raise ValueError("At least one approved feature is required for social drafts")
    if language not in {"ja", "en"}:
        raise ValueError("Unsupported post language")
    ja = language == "ja"
    title, detail = features[0]
    clean_title = title.rstrip("。.!！?？")
    points = "\n".join(f"{i}. {t} — {d}" for i, (t, d) in enumerate(features[:3], 1))
    if channel == "x":
        return f"{name} — {title}\n\n{detail}\n\n" + ("紹介動画を見る。" if ja else "Watch the product overview.")
    if channel == "bluesky":
        return f"{title}\n\n{name}: {detail}\n\n" + ("紹介と詳細はこちら。" if ja else "Explore the overview and project.")
    if channel == "threads":
        return (f"「{clean_title}」を詳しく。\n\n{name}\n{detail}\n\n紹介動画と詳細はこちら。" if ja
                else f"A closer look: {clean_title}\n\n{name}\n{detail}\n\nSee the overview and project details.")
    if channel == "linkedin":
        return (f"{audience}へ\n\n{name} — {tagline}\n\n紹介する機能\n{points}\n\n紹介と利用条件を確認する。" if ja
                else f"For {audience}\n\n{name} — {tagline}\n\nFeatures in this overview\n{points}\n\nExplore the overview.")
    if channel == "youtube":
        return f"{name} | {tagline}\n\n" + ("この動画で紹介する機能\n" if ja else "Features in this video\n") + points + ("\n\n製品と利用条件はこちら。" if ja else "\n\nProduct details and requirements:")
    if channel == "instagram":
        return f"{tagline}\n\n{name}\n\n{title}\n{detail}\n\n" + ("紹介動画を見る。" if ja else "Watch the overview.")
    if channel == "tiktok":
        return f"{name}\n{title}\n\n" + ("紹介する機能 → " if ja else "Featured capability → ") + detail
    raise ValueError(f"Unsupported social channel: {channel}")


def fit_post(body: str, url: str, limit: int, measure: Callable[[str], int]) -> str:
    """Keep the full destination URL, visibly shorten the copy, or fail clearly."""
    tail = "\n\n" + url if url else ""
    if measure(body + tail) <= limit:
        return body + tail
    if measure("…" + tail) > limit:
        raise ValueError("The destination URL alone exceeds the draft limit")
    shortened = body
    while shortened and measure(shortened.rstrip() + "…" + tail) > limit:
        shortened = shortened[:-1]
    return shortened.rstrip() + "…" + tail
