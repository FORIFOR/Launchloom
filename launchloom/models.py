from __future__ import annotations
import re
from typing import Any, Literal
from urllib.parse import urlsplit
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class Feature(StrictModel):
    title: str = Field(min_length=1, max_length=60)
    detail: str = Field(min_length=1, max_length=180)
    evidence: str = Field(default="", max_length=400)
    approved: bool = False

class CaptureStep(StrictModel):
    action: Literal["click", "fill", "scroll", "wait"]
    selector: str = Field(default="", max_length=240)
    value: str = Field(default="", max_length=500)
    label: str = Field(default="", max_length=70)
    milliseconds: int = Field(default=1200, ge=100, le=5000)
    delta_y: int = Field(default=450, ge=-1500, le=1500)
    @model_validator(mode="after")
    def check(self):
        if self.action in {"click", "fill"} and not self.selector:
            raise ValueError("click/fill requires a selector")
        return self

class Brief(StrictModel):
    name: str = Field(min_length=1, max_length=40)
    tagline: str = Field(min_length=1, max_length=90)
    audience: str = Field(min_length=1, max_length=140)
    description: str = Field(default="", max_length=1000)
    product_url: str = Field(default="", max_length=1500)
    features: list[Feature] = Field(min_length=1, max_length=8)
    accent: str = "#ed6847"
    language: Literal["ja", "en"] = "ja"
    goal: Literal["signups", "demos", "github"] = "signups"
    channels: list[Literal["x", "linkedin", "threads", "bluesky", "youtube", "instagram", "tiktok"]] = Field(default_factory=lambda: ["x", "linkedin", "threads"], min_length=1, max_length=7)
    references: list[str] = Field(default_factory=list, max_length=10)
    is_sample: bool = False
    @field_validator("accent")
    @classmethod
    def color(cls, value):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
            raise ValueError("accent must be #RRGGBB")
        return value
    @field_validator("product_url")
    @classmethod
    def product_link(cls, value):
        if value:
            u = urlsplit(value)
            if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
                raise ValueError("Use an http(s) product URL without embedded credentials")
        return value
    @model_validator(mode="after")
    def approved_evidence(self):
        if len(set(self.channels)) != len(self.channels):
            raise ValueError("Duplicate channels are not allowed")
        for feature in self.features:
            if feature.approved and not feature.evidence:
                raise ValueError("Approved features require an evidence note")
        return self

class BuildOptions(StrictModel):
    capture_mode: Literal["sample", "url", "upload", "none"] = "none"
    capture_url: str = Field(default="", max_length=1500)
    steps: list[CaptureStep] = Field(default_factory=list, max_length=12)
    redact_selectors: list[str] = Field(default_factory=list, max_length=30)
    allow_site_writes: bool = False
    staging_confirmed: bool = False
    film_provider: Literal["local", "fal", "comfy"] = "local"
    provider_input: dict[str, Any] = Field(default_factory=dict)
    estimated_cost_usd: float = Field(default=0, ge=0, le=100)
    external_data_consent: bool = False
    llm_plan: bool = False
    quality: Literal["draft", "hd"] = "hd"
    @model_validator(mode="after")
    def guard(self):
        if self.capture_mode == "url" and (not self.capture_url or not self.staging_confirmed):
            raise ValueError("URL capture needs a URL and explicit staging/test-data confirmation")
        if self.allow_site_writes and not self.staging_confirmed:
            raise ValueError("Site writes require staging/test-data confirmation")
        if (self.film_provider != "local" or self.llm_plan) and not self.external_data_consent:
            raise ValueError("Explicit external-data consent is required for configured AI providers")
        if self.film_provider == "fal" and self.estimated_cost_usd <= 0:
            raise ValueError("Provide a current cost estimate before requesting a paid generation")
        return self

class Scene(StrictModel):
    kind: Literal["hook", "proof", "cta"]
    title: str = Field(max_length=90)
    detail: str = Field(default="", max_length=180)
    feature_index: int | None = None

class Plan(StrictModel):
    concept: str = Field(max_length=300)
    visual_direction: str = Field(max_length=500)
    scenes: list[Scene] = Field(min_length=3, max_length=6)
    video_prompt: str = Field(max_length=1800)
    source: Literal["local-template", "configured-llm"] = "local-template"

class PublicationDraft(StrictModel):
    channel: Literal["x", "linkedin", "threads", "bluesky", "youtube", "instagram", "tiktok"]
    content: str = Field(min_length=1, max_length=5000)
    integration_id: str = Field(min_length=1, max_length=200)
    media: Literal["landscape.mp4", "portrait.mp4"] = "landscape.mp4"
    schedule_at: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)

class Approval(StrictModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    content_reviewed: bool
    rights_confirmed: bool
    account_authorized: bool
    @model_validator(mode="after")
    def all_checked(self):
        if not all([self.content_reviewed, self.rights_confirmed, self.account_authorized]):
            raise ValueError("Review content, confirm asset rights, and authorize the destination account")
        return self
