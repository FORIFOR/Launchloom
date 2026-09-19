"""Versioned, renderer-neutral creative data. No network or code execution."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Output = Literal["landscape", "portrait"]
Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")]


class CreativeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False, revalidate_instances="always")

    @field_validator("*", mode="before")
    @classmethod
    def no_nonfinite_or_control(cls, value):
        if isinstance(value, str) and any(ord(c) < 32 and c not in "\n\t" for c in value):
            raise ValueError("Control characters are not allowed")
        return value


class BrandProfile(CreativeModel):
    name: str = Field(min_length=1, max_length=80)
    audience: str = Field(default="", max_length=180)
    promise: str = Field(default="", max_length=240)
    visual_direction: str = Field(default="", max_length=600)
    motion_direction: str = Field(default="", max_length=400)
    voice_direction: str = Field(default="", max_length=400)
    signature: str = Field(default="", max_length=240)
    avoid: list[Annotated[str, Field(max_length=180)]] = Field(default_factory=list, max_length=20)
    # These two fields have a deterministic meaning in the standard renderer.
    # The prose directions are retained for future/provider-specific interpretation.
    preset: Literal["editorial", "spotlight", "grid"] = "editorial"
    accent: str = Field(default="#A83B2F", pattern=r"^#[0-9a-fA-F]{6}$")


class CaptionLayout(CreativeModel):
    y: float = Field(default=0.78, ge=0.10, le=0.90)
    size: float = Field(default=0.055, ge=0.025, le=0.10)

    @field_validator("y", "size", mode="before")
    @classmethod
    def numbers(cls, value):
        if type(value) not in (int, float):
            raise ValueError("Layout values must be numbers, not strings or booleans")
        return value


class CreativeLayer(CreativeModel):
    id: Identifier
    kind: Literal["recording", "generated_video", "text", "shape", "image", "audio"]
    role: Literal["evidence", "concept", "copy", "decoration", "music", "narration"]
    asset_id: str = Field(default="", pattern=r"^(?:[a-z][a-z0-9_-]{0,79})?$")
    asset_sha256: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    text: str = Field(default="", max_length=500)
    generator: str = Field(default="", max_length=80)
    start_seconds: float = Field(default=0, ge=0, le=300)

    @field_validator("start_seconds", mode="before")
    @classmethod
    def numeric_start(cls, value):
        if type(value) not in (int, float):
            raise ValueError("start_seconds must be numeric")
        return value

    @model_validator(mode="after")
    def content_matches_kind(self):
        roles = {"recording": {"evidence", "concept"}, "generated_video": {"concept"},
                 "text": {"copy"}, "shape": {"decoration"}, "image": {"concept", "decoration"},
                 "audio": {"music", "narration"}}
        if self.role not in roles[self.kind]:
            raise ValueError("Only a real recording can be an evidence layer")
        if self.kind == "text" and not self.text:
            raise ValueError("Text layers require text")
        if self.kind in {"recording", "image", "audio"} and not self.asset_id:
            raise ValueError(f"{self.kind} layers require asset_id")
        if self.kind == "generated_video" and not (self.asset_id or self.generator):
            raise ValueError("Generated video needs an asset or generator")
        if self.kind in {"text", "shape"} and (self.asset_id or self.asset_sha256 or self.generator or self.start_seconds):
            raise ValueError("Text and shape layers cannot reference media or providers")
        return self


class CreativeScene(CreativeModel):
    id: Identifier
    purpose: Literal["hook", "problem", "proof", "transition", "cta"]
    title: str = Field(default="", max_length=90)
    seconds: float = Field(ge=0.5, le=30)
    claim_ids: list[Annotated[str, Field(pattern=r"^feature-[0-7]$")]] = Field(default_factory=list, max_length=8)
    layers: list[CreativeLayer] = Field(min_length=1, max_length=20)
    camera: Literal["hold", "gentle_zoom", "follow_action", "custom"] = "hold"
    layouts: dict[Output, CaptionLayout] = Field(default_factory=dict)

    @field_validator("seconds", mode="before")
    @classmethod
    def numeric_seconds(cls, value):
        if type(value) not in (int, float):
            raise ValueError("seconds must be numeric")
        return value

    @model_validator(mode="after")
    def evidence_and_ids(self):
        if self.purpose == "proof" and not any(x.role == "evidence" for x in self.layers):
            raise ValueError("Proof scenes require a real recording evidence layer")
        ids = [x.id for x in self.layers]
        if len(ids) != len(set(ids)) or len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("Layer ids and claim ids must be unique within a scene")
        return self


class CreativeSpec(CreativeModel):
    schema_version: Literal[2] = 2
    title: str = Field(min_length=1, max_length=80, pattern=r"^[^\x00-\x1f]+$")
    fps: Literal[24, 25, 30] = 30
    outputs: list[Output] = Field(default_factory=lambda: ["landscape", "portrait"], min_length=1, max_length=2)
    brand: BrandProfile
    scenes: list[CreativeScene] = Field(min_length=1, max_length=20)

    @field_validator("fps", "schema_version", mode="before")
    @classmethod
    def integer_values(cls, value):
        if type(value) is not int:
            raise ValueError("fps and schema_version must be integers")
        return value

    @model_validator(mode="after")
    def structure(self):
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("Outputs must be unique")
        ids = [x.id for x in self.scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("Scene ids must be unique")
        if sum(x.seconds for x in self.scenes) > 180:
            raise ValueError("Creative spec must not exceed 180 seconds")
        return self


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    allow_nan=False, separators=(",", ":")).encode()).hexdigest()


def creative_revision(spec: CreativeSpec | dict) -> str:
    return fingerprint(CreativeSpec.model_validate(spec).model_dump())


def from_production_plan(plan: dict, brief: dict) -> CreativeSpec:
    """Keep v1 compatible; preserve original feature indexes, including unapproved gaps."""
    from .production import validate_plan
    plan = validate_plan(plan)
    by_title: dict[str, list[str]] = {}
    for i, feature in enumerate(brief.get("features", [])):
        if feature.get("approved") is True:
            by_title.setdefault(feature.get("title", ""), []).append(f"feature-{i}")
    scenes = []
    for item in plan["scenes"]:
        source = item["source"]
        if source == "recording":
            layers = [CreativeLayer(id="product", kind="recording", role="evidence", asset_id=item["id"])]
            purpose = "proof"
        elif source == "seedance":
            layers = [CreativeLayer(id="atmosphere", kind="generated_video", role="concept", generator="seedance")]
            purpose = "hook"
        else:
            layers = [CreativeLayer(id="ground", kind="shape", role="decoration")]
            purpose = "cta"
        layers.append(CreativeLayer(id="headline", kind="text", role="copy", text=item["title"]))
        # Ambiguous equal titles must be resolved by the operator, not guessed.
        claims = by_title.get(item["title"], [])
        scenes.append(CreativeScene(id=item["id"], purpose=purpose, title=item["title"],
                      seconds=item["seconds"], claim_ids=claims if len(claims) == 1 else [], layers=layers))
    brand = BrandProfile(name=brief.get("name", plan["title"]), audience=brief.get("audience", ""),
                         promise=brief.get("tagline", ""), accent=brief.get("accent", "#A83B2F"),
                         visual_direction="Product-led, restrained editorial composition.",
                         motion_direction="Motion explains value; surrounding UI stays calm.",
                         signature="One memorable product transition.",
                         avoid=["fabricated product UI", "unsupported claims", "decorative AI clichés"])
    return CreativeSpec(title=plan["title"], fps=plan["fps"], brand=brand, scenes=scenes)


def changed_scene_ids(before: CreativeSpec | dict, after: CreativeSpec | dict) -> set[str]:
    """Local payload diff only. NOT a complete render-cache invalidation policy."""
    a = {x.id: x.model_dump() for x in CreativeSpec.model_validate(before).scenes}
    b = {x.id: x.model_dump() for x in CreativeSpec.model_validate(after).scenes}
    return {sid for sid in a.keys() | b.keys() if a.get(sid) != b.get(sid)}


def scene_render_key(spec: CreativeSpec, scene: CreativeScene, output: Output, assets: dict,
                     renderer: str, fonts: str) -> str:
    """Include all global dependencies, but only the selected aspect's layout.

    Reordering scenes changes the assembly, not individual scene renders. Asset
    bytes and renderer/font versions participate even if scene text did not change.
    """
    if output not in spec.outputs:
        raise ValueError("Output is not enabled")
    payload = scene.model_dump(exclude={"layouts"})
    payload["frames"] = round(scene.seconds * spec.fps)
    payload["layout"] = scene.layouts.get(output, CaptionLayout()).model_dump()
    used = {x.asset_id: assets[x.asset_id]["sha256"] for x in scene.layers if x.asset_id}
    return fingerprint({"scene": payload, "brand": spec.brand.model_dump(), "fps": spec.fps,
                        "output": output, "assets": used, "renderer": renderer, "fonts": fonts})
