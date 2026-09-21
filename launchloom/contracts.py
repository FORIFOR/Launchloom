"""HTTP response contracts for the local v0.1 studio; business rules stay in Store.

Responses may gain fields. Requests continue to use the strict existing models.
Experimental production/creative workflows have their own revision contracts.
"""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field
from .models import Brief, BuildOptions, Plan

CampaignState = Literal['draft', 'queued', 'building', 'awaiting_review', 'ready', 'failed', 'interrupted']


class CampaignRecord(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    brief: Brief
    options: BuildOptions | None = None
    plan: Plan | None = None
    state: CampaignState
    progress: int = Field(ge=0, le=100)
    stage: str
    error: str | None = None
    created: float
    plan_approved: int
    revision: int
    released: int


class CampaignSnapshot(CampaignRecord):
    outputs: dict[str, str]
    events: list[dict[str, Any]]
    publications: list[dict[str, Any]]
    metrics: dict[str, Any]
    final_films: list[dict[str, Any]]
    posts: list[dict[str, Any]] | None = None
    qa: dict[str, Any] | None = None
    manifest: dict[str, Any] | None = None


class BuildJob(BaseModel):
    id: str
    campaign_id: str
    state: Literal['queued', 'running', 'complete', 'failed', 'interrupted']
    options: BuildOptions
    created: float
    started: float | None = None
    ended: float | None = None


class APIError(BaseModel):
    detail: str | list[dict[str, Any]]


TASK_ERRORS = {code: {'model': APIError, 'description': description} for code, description in {
    401: 'Local bearer token or session required',
    403: 'Cross-origin write rejected',
    404: 'Campaign not found',
    409: 'Operation conflicts with saved state or idempotency key',
    422: 'Invalid input, options or consent; detail is a message or validation errors',
}.items()}
