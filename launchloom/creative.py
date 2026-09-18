"""Declarative creative specification shared by planning, renderers and review UI.

This module intentionally contains no provider or renderer execution. It describes
what a scene means and which layers it contains so generation tools, recordings and
composition engines do not become the product's data model.
"""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel


class BrandProfile(StrictModel):
    """Reusable direction for a product without reducing a brand to an accent colour."""

    name: str = Field(min_length=1, max_length=80)
    audience: str = Field(default="", max_length=180)
    promise: str = Field(default="", max_length=240)
    visual_direction: str = Field(default="", max_length=600)
    motion_direction: str = Field(default="", max_length=400)
    voice_direction: str = Field(default="", max_length=400)
    signature: str = Field(default="", max_length=240)
    avoid: list[str] = Field(default_factory=list, max_length=20)


class CreativeLayer(StrictModel):
    """One independently replaceable layer in a scene."""

    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    kind: Literal["recording", "generated_video", "text", "shape", "image", "audio"]
    role: Literal["evidence", "concept", "copy", "decoration", "music", "narration"]
    asset_id: str = Field(default="", max_length=120)
    text: str = Field(default="", max_length=500)
    generator: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def content_matches_kind(self):
        if self.kind == "text" and not self.text:
            raise ValueError("Text layers require text")
        if self.kind in {"recording", "image", "audio"} and not self.asset_id:
            raise ValueError(f"{self.kind} layers require asset_id")
        if self.kind == "generated_video" and not (self.asset_id or self.generator):
            raise ValueError("Generated video needs an existing asset or a generator")
        if self.role == "evidence" and self.kind == "generated_video":
            raise ValueError("Generated video cannot be product evidence")
        return self


class CreativeScene(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    purpose: Literal["hook", "problem", "proof", "transition", "cta"]
    title: str = Field(default="", max_length=90)
    seconds: float = Field(ge=0.5, le=30)
    claim_ids: list[str] = Field(default_factory=list, max_length=8)
    layers: list[CreativeLayer] = Field(min_length=1, max_length=20)
    camera: Literal["hold", "gentle_zoom", "follow_action", "custom"] = "hold"

    @model_validator(mode="after")
    def proof_requires_evidence(self):
        if self.purpose == "proof" and not any(layer.role == "evidence" for layer in self.layers):
            raise ValueError("Proof scenes require at least one evidence layer")
        ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValueError("Layer ids must be unique within a scene")
        return self


class CreativeSpec(StrictModel):
    """Renderer-neutral campaign source of truth."""

    schema_version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=80)
    fps: Literal[24, 25, 30] = 30
    outputs: list[Literal["landscape", "portrait"]] = Field(
        default_factory=lambda: ["landscape", "portrait"], min_length=1, max_length=2
    )
    brand: BrandProfile
    scenes: list[CreativeScene] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_structure(self):
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("Outputs must be unique")
        ids = [scene.id for scene in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene ids must be unique")
        if sum(scene.seconds for scene in self.scenes) > 180:
            raise ValueError("Creative spec must not exceed 180 seconds")
        return self


def creative_revision(spec: CreativeSpec | dict) -> str:
    value = CreativeSpec.model_validate(spec).model_dump()
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def from_production_plan(plan: dict, brief: dict) -> CreativeSpec:
    """Lift the legacy source-per-scene plan into a renderer-neutral layered spec.

    This adapter keeps the current production board compatible while new renderers
    and UI can adopt the v2 contract incrementally.
    """
    from .production import validate_plan

    plan = validate_plan(plan)
    approved = [f for f in brief.get("features", []) if f.get("approved") is True]
    claim_by_title = {f.get("title", ""): f"feature-{i}" for i, f in enumerate(approved)}
    scenes: list[CreativeScene] = []

    for scene in plan["scenes"]:
        source = scene["source"]
        if source == "recording":
            layers = [
                CreativeLayer(id="product", kind="recording", role="evidence", asset_id=scene["id"]),
                CreativeLayer(id="headline", kind="text", role="copy", text=scene["title"]),
            ]
            purpose = "proof"
        elif source == "seedance":
            layers = [
                CreativeLayer(id="atmosphere", kind="generated_video", role="concept", generator="seedance"),
                CreativeLayer(id="headline", kind="text", role="copy", text=scene["title"]),
            ]
            purpose = "hook"
        else:
            layers = [
                CreativeLayer(id="headline", kind="text", role="copy", text=scene["title"]),
                CreativeLayer(id="ground", kind="shape", role="decoration"),
            ]
            purpose = "cta"

        claim = claim_by_title.get(scene["title"])
        scenes.append(CreativeScene(
            id=scene["id"],
            purpose=purpose,
            title=scene["title"],
            seconds=scene["seconds"],
            claim_ids=[claim] if claim else [],
            layers=layers,
            camera="follow_action" if source == "recording" else "hold",
        ))

    brand = BrandProfile(
        name=brief.get("name", plan["title"]),
        audience=brief.get("audience", ""),
        promise=brief.get("tagline", ""),
        visual_direction="Product-led, restrained editorial composition.",
        motion_direction="Motion explains value; surrounding UI stays calm.",
        signature="One memorable product transition.",
        avoid=["fabricated product UI", "unsupported claims", "decorative AI clichés"],
    )
    return CreativeSpec(title=plan["title"], fps=plan["fps"], brand=brand, scenes=scenes)


def changed_scene_ids(before: CreativeSpec | dict, after: CreativeSpec | dict) -> set[str]:
    """Return only scenes whose declarative payload changed.

    This is the primitive used by partial re-rendering: unchanged generated clips
    and recordings can be retained rather than spending or capturing again.
    """
    left = CreativeSpec.model_validate(before)
    right = CreativeSpec.model_validate(after)
    a = {scene.id: scene.model_dump() for scene in left.scenes}
    b = {scene.id: scene.model_dump() for scene in right.scenes}
    return {sid for sid in set(a) | set(b) if a.get(sid) != b.get(sid)}
