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
        if len(self.token) < 24:
            raise ValueError("LAUNCHLOOM_TOKEN must have at least 24 characters")
