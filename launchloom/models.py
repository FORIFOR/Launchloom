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

class CaptureEvent(StrictModel):
    """A moment in an imported recording: what happened, where, and when.

    Supplied by the operator for uploaded footage, which carries no cursor
    metadata of its own. Coordinates are fractions of the frame."""
    time: float = Field(ge=0, le=300)
    label: str = Field(default="", max_length=70)
    action: Literal["click", "fill", "scroll"] = "click"
    x: float = Field(default=0.5, ge=0, le=1)
    y: float = Field(default=0.5, ge=0, le=1)


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
    # Stop after capture so scenes can be read and reworded before any rendering.
    review_plan: bool = False
    visual_style: Literal["editorial", "spotlight", "grid"] = "editorial"
    capture_events: list[CaptureEvent] = Field(default_factory=list, max_length=24)
    # Which part of the recording becomes the proof section. 0 length means
    # "from the start point, up to the built-in 20 second ceiling".
    capture_start: float = Field(default=0, ge=0, le=290)
    capture_length: float = Field(default=0, ge=0, le=120)
    # How long the motion-graphics section runs when there is no recording.
    # With footage, the recording's own length decides.
    animation_seconds: float = Field(default=9, ge=4, le=30)
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
        if self.capture_events and self.capture_mode != "upload":
            raise ValueError("An imported event track belongs to uploaded footage; recorded captures time themselves")
        if self.capture_events != sorted(self.capture_events, key=lambda e: e.time):
            raise ValueError("Imported events must be ordered by time")
        if self.capture_length and self.capture_length < 1:
            raise ValueError("A trimmed range needs at least one second of footage")
        if (self.capture_start or self.capture_length) and self.capture_mode == "none":
            raise ValueError("There is no recording to trim")
        return self

class Scene(StrictModel):
    kind: Literal["hook", "proof", "cta"]
    title: str = Field(max_length=90)
    detail: str = Field(default="", max_length=180)
    feature_index: int | None = None
    # Empty means "use the title". Captions are on-screen scene headings, not a
    # transcript of speech, so the operator can word them differently.
    caption: str = Field(default="", max_length=120)

class Plan(StrictModel):
    concept: str = Field(max_length=300)
    visual_direction: str = Field(max_length=500)
    scenes: list[Scene] = Field(min_length=3, max_length=6)
    video_prompt: str = Field(max_length=1800)
    source: Literal["local-template", "configured-llm", "operator-edited"] = "local-template"

class SceneEdit(StrictModel):
    """One scene's operator wording. The scene's kind and the feature it points at
    are structural and stay where the brief put them."""
    index: int = Field(ge=0, le=5)
    title: str | None = Field(default=None, min_length=1, max_length=90)
    detail: str | None = Field(default=None, max_length=180)
    caption: str | None = Field(default=None, max_length=120)


class PlanEdit(StrictModel):
    concept: str | None = Field(default=None, max_length=300)
    visual_direction: str | None = Field(default=None, max_length=500)
    scenes: list[SceneEdit] = Field(default_factory=list, max_length=6)
    @model_validator(mode="after")
    def one_edit_per_scene(self):
        indexes=[s.index for s in self.scenes]
        if len(set(indexes)) != len(indexes):
            raise ValueError("Each scene can be edited once per request")
        if not self.scenes and self.concept is None and self.visual_direction is None:
            raise ValueError("Nothing to change")
        return self


class PublicationDraft(StrictModel):
    channel: Literal["x", "linkedin", "threads", "bluesky", "youtube", "instagram", "tiktok"]
    content: str = Field(min_length=1, max_length=5000)
    integration_id: str = Field(min_length=1, max_length=200)
    media: str = Field(default="landscape.mp4", pattern=r"^(?:landscape\.mp4|portrait\.mp4|finals/[a-f0-9]{16}\.mp4)$")
    schedule_at: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)

class Reconciliation(StrictModel):
    """What the operator found when they looked at the platform themselves.

    Launchloom never decides this. A timeout proves nothing either way, so the
    only way out of `needs_reconciliation` is a person reporting what exists."""
    resolution: Literal["published", "not_published"]
    remote_id: str = Field(default="", max_length=200)
    note: str = Field(default="", max_length=400)
    @model_validator(mode="after")
    def evidence(self):
        if self.resolution == "published" and not self.remote_id:
            raise ValueError("Give the post id you found, so the record points at the real post")
        return self


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
