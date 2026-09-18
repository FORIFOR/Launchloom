from __future__ import annotations
import os
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LAUNCHLOOM_DATA", ".launchloom")).resolve())
    host: str = field(default_factory=lambda: os.getenv("LAUNCHLOOM_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("LAUNCHLOOM_PORT", "8787")))
    token: str = field(default_factory=lambda: os.getenv("LAUNCHLOOM_TOKEN", ""))
    chromium: str | None = field(default_factory=lambda: os.getenv("CHROMIUM_EXECUTABLE") or shutil.which("chromium") or shutil.which("chromium-browser"))
    no_sandbox: bool = field(default_factory=lambda: os.getenv("CHROMIUM_NO_SANDBOX") == "1")
    capture_origins: str = field(default_factory=lambda: os.getenv("CAPTURE_ALLOWED_ORIGINS", ""))
    llm_base: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    fal_key: str = field(default_factory=lambda: os.getenv("FAL_KEY", ""))
    fal_model: str = field(default_factory=lambda: os.getenv("FAL_MODEL", ""))
    comfy_base: str = field(default_factory=lambda: os.getenv("COMFY_BASE_URL", ""))
    postiz_base: str = field(default_factory=lambda: os.getenv("POSTIZ_BASE_URL", ""))
    postiz_key: str = field(default_factory=lambda: os.getenv("POSTIZ_API_KEY", ""))
    tracking_base: str = field(default_factory=lambda: os.getenv("PUBLIC_TRACKING_BASE", ""))
    enable_live_publish: bool = field(default_factory=lambda: os.getenv("ENABLE_LIVE_PUBLISH") == "1")
    enable_paid_generation: bool = field(default_factory=lambda: os.getenv("ENABLE_PAID_GENERATION") == "1")
    budget_usd: float = field(default_factory=lambda: float(os.getenv("GENERATION_BUDGET_USD", "0")))
    secure_cookie: bool = field(default_factory=lambda: os.getenv("SECURE_COOKIE") == "1")
    # Pacing guards: a launch should not turn into a burst on one account.
    max_posts_per_channel_per_day: int = field(default_factory=lambda: int(os.getenv("MAX_POSTS_PER_CHANNEL_PER_DAY", "3")))
    min_post_gap_minutes: int = field(default_factory=lambda: int(os.getenv("MIN_POST_GAP_MINUTES", "30")))
    deploy_dir: str = field(default_factory=lambda: os.getenv("SITE_DEPLOY_DIR", ""))
    # Production execution is separate from save/export and remains opt-in.
    seedance_price_per_1k_tokens_usd: float = field(default_factory=lambda: float(os.getenv("SEEDANCE_PRICE_PER_1K_TOKENS_USD", "0.0214")))
    enable_local_agents: bool = field(default_factory=lambda: os.getenv("ENABLE_LOCAL_AGENTS") == "1")
    codex_executable: str | None = field(default_factory=lambda: os.getenv("CODEX_EXECUTABLE") or shutil.which("codex"))
    claude_executable: str | None = field(default_factory=lambda: os.getenv("CLAUDE_EXECUTABLE") or shutil.which("claude"))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    production_execution_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("PRODUCTION_EXECUTION_TIMEOUT_SECONDS", "600")))
    enable_after_effects: bool = field(default_factory=lambda: os.getenv("ENABLE_AFTER_EFFECTS") == "1")
    afterfx_executable: str | None = field(default_factory=lambda: os.getenv("AFTERFX_EXECUTABLE") or None)
    aerender_executable: str | None = field(default_factory=lambda: os.getenv("AERENDER_EXECUTABLE") or shutil.which("aerender"))

    # Optional creative assistant. Separate from the legacy LLM planning switch.
    enable_creative_ai: bool = field(default_factory=lambda: os.getenv("ENABLE_CREATIVE_AI") == "1")
    enable_creative_vision: bool = field(default_factory=lambda: os.getenv("ENABLE_CREATIVE_VISION") == "1")
    creative_ai_json_mode: bool = field(default_factory=lambda: os.getenv("CREATIVE_AI_JSON_MODE", "1") == "1")
    creative_ai_max_tokens: int = field(default_factory=lambda: int(os.getenv("CREATIVE_AI_MAX_TOKENS", "2400")))

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.data_dir / "campaigns").mkdir(exist_ok=True)
        token_file = self.data_dir / "access-token"
        if not self.token:
            if token_file.exists():
                self.token = token_file.read_text().strip()
            else:
                self.token = secrets.token_urlsafe(32)
                token_file.write_text(self.token)
                token_file.chmod(0o600)
        if not 256 <= self.creative_ai_max_tokens <= 8000:
            raise ValueError("CREATIVE_AI_MAX_TOKENS must be 256–8000")
        if len(self.token) < 24:
            raise ValueError("LAUNCHLOOM_TOKEN must have at least 24 characters")
        if not 10 <= self.production_execution_timeout_seconds <= 3600:
            raise ValueError("PRODUCTION_EXECUTION_TIMEOUT_SECONDS must be 10–3600")
        if not 0 < self.seedance_price_per_1k_tokens_usd <= 10:
            raise ValueError("SEEDANCE_PRICE_PER_1K_TOKENS_USD must be positive")
