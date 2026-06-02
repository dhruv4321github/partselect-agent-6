"""Application configuration.

All settings come from environment variables so the same code runs against
Anthropic or any OpenAI-compatible provider (OpenAI, Deepseek, Groq, ...).
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass
class Settings:
    # "anthropic" (default) or "openai" (covers OpenAI / Deepseek / Groq / any
    # OpenAI-compatible endpoint via LLM_BASE_URL).
    provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic").lower())
    model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-sonnet-4-6"))
    api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))
    # Only used for OpenAI-compatible providers. e.g. Deepseek -> https://api.deepseek.com
    base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    max_tokens: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_TOKENS", "1024")))
    # Safety valve so a misbehaving model can't loop forever calling tools.
    max_tool_steps: int = field(default_factory=lambda: int(os.getenv("MAX_TOOL_STEPS", "6")))
    # Comma-separated CORS origins for the React dev server / deployment.
    cors_origins: list = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
    )

    # ---- Live catalog fetch (hybrid mode) ------------------------------
    # OFF by default. PartSelect's CDN (Akamai) returns 403 to server-side
    # requests, so live fetch only works if you install curl_cffi (browser TLS
    # impersonation) AND set LIVE_FETCH=true. With it off, the app serves the
    # curated catalog in data/*.json — a reliable, fully offline demo.
    live_fetch: bool = field(
        default_factory=lambda: os.getenv("LIVE_FETCH", "false").lower() in ("1", "true", "yes")
    )
    # Polite delay (seconds) between live requests.
    live_delay: float = field(default_factory=lambda: float(os.getenv("LIVE_DELAY", "1.5")))
    # Disk cache directory for fetched pages + resolved data.
    live_cache_dir: str = field(
        default_factory=lambda: os.getenv("LIVE_CACHE_DIR", str(DATA_DIR / ".live_cache"))
    )
    # Resolve bare PS numbers to part URLs via the sitemap index. On by default so
    # "install part PSxxxx" works for any real part; the first such lookup builds a
    # one-time, cached index (~10-30s). Set false to skip (model lookups still work).
    live_resolve_via_sitemap: bool = field(
        default_factory=lambda: os.getenv("LIVE_RESOLVE_VIA_SITEMAP", "true").lower()
        in ("1", "true", "yes")
    )

    def fallback_api_key(self) -> str:
        """If LLM_API_KEY isn't set, fall back to the provider's conventional env var."""
        if self.api_key:
            return self.api_key
        if self.provider == "anthropic":
            return os.getenv("ANTHROPIC_API_KEY", "")
        return os.getenv("OPENAI_API_KEY", "")


settings = Settings()
