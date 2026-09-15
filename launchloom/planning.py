from __future__ import annotations
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from .models import Brief, Plan, Scene, PlanEdit


def make_plan(b: Brief, visual_style: str='editorial') -> Plan:
    approved=[(i,f) for i,f in enumerate(b.features) if f.approved]
    if not approved: raise ValueError("At least one feature must be approved with an evidence note before building")
    ja=b.language=='ja'
    from .rendering import STYLES
    direction=STYLES.get(visual_style,STYLES['editorial'])['direction']
    return Plan(concept=f"{b.audience}に、{b.name}を説明する前に使う場面を見せる。" if ja else f"Show {b.audience} the change {b.name} makes before explaining it.",
        visual_direction=direction+" No fabricated screens or performance claims.",
        scenes=[Scene(kind='hook',title=b.tagline,detail=b.audience)]+[
            Scene(kind='proof',title=f.title,detail=f.detail,feature_index=i) for i,f in approved[:3]
        ]+[Scene(kind='cta',title=f"{b.name}を、次の一歩に。" if ja else f"Make room for {b.name}.",detail="実際に試してみる" if ja else "Try it for yourself.")],
        video_prompt=f"Create an ORIGINAL short cinematic atmospheric opening for {b.name}. Audience: {b.audience}. Feeling: {b.tagline}. Tactile light, a coherent world, one surprising visual transition. No text, no logos, no simulated product UI, no imitation of a named creator, no real-person likeness. This is an explicitly AI-generated conceptual opening, not documentary product evidence.")


def with_utm(url: str, channel: str, cid: str, variant='a') -> str:
    if not url:return ''
    p=urlsplit(url)
    query=dict(parse_qsl(p.query,keep_blank_values=True))
    query.update(utm_source=channel,utm_medium='social',utm_campaign=cid,utm_content=variant)
    return urlunsplit((p.scheme,p.netloc,p.path,urlencode(query),p.fragment))


def x_weight(text: str) -> int:
    """Conservative preflight, NOT a replacement for platform validation."""
    text=re.sub(r'https?://\S+', 'x'*23,text)
    def weight(ch):
        n=ord(ch)
        return 1 if n<=0x10ff or 0x2000<=n<=0x200d or 0x2010<=n<=0x201f or 0x2032<=n<=0x2037 else 2
    return sum(map(weight,text))


def make_posts(b: Brief,cid: str) -> list[dict]:
    from .post_copy import compose_post_copy, fit_post
    approved=[f for f in b.features if f.approved]
    if not approved:
        raise ValueError("At least one approved feature is required for social drafts")
    result=[]
    for channel in b.channels:
        url=with_utm(b.product_url,channel,cid)
        base=compose_post_copy(name=b.name,tagline=b.tagline,audience=b.audience,
            features=[(f.title,f.detail) for f in approved],channel=channel,language=b.language)
        content=base+('\n\n'+url if url else '')
        if channel in {'x','bluesky'}:
            content=fit_post(base,url,280 if channel=='x' else 300,x_weight if channel=='x' else len)
        result.append({"channel":channel,"variant":"a","content":content,
            "media":"portrait.mp4" if channel in {'instagram','tiktok','youtube'} else 'landscape.mp4',
            "utm_url":url,"state":"draft","warning":None if url else "公開先URLが未設定です。ローカルプレビューURLは投稿しません。",
            "hook_variants":[b.tagline,approved[0].title]})
    return result


def apply_plan_edit(plan: dict, edit: PlanEdit) -> dict:
    """Rewrite the operator's own words in a storyboard.

    Scene kinds and feature links are structural and stay as planned, so an edit
    cannot silently attach a rewritten claim to a different approved feature."""
    current=Plan.model_validate(plan)
    if edit.concept is not None: current.concept=edit.concept
    if edit.visual_direction is not None: current.visual_direction=edit.visual_direction
    for change in edit.scenes:
        if change.index>=len(current.scenes):
            raise ValueError("Scene %d is not in this storyboard" % change.index)
        scene=current.scenes[change.index]
        if change.title is not None: scene.title=change.title
        if change.detail is not None: scene.detail=change.detail
        if change.caption is not None: scene.caption=change.caption
    current.source='operator-edited'
    return Plan.model_validate(current.model_dump()).model_dump()
