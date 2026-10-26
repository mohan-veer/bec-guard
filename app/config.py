"""Settings from environment variables. Mock mode is decided per service."""
import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env once at import; real env vars win over .env values.
load_dotenv(override=False)

log = logging.getLogger("bec_guard")


@dataclass(frozen=True)
class Settings:
    nebius_api_key: str
    nebius_base_url: str
    tavily_api_key: str
    mock_mode: bool
    model_nano: str
    model_super: str
    model_vl: str
    model_ultra: str
    guardian_report_url: str
    guardian_interval_minutes: int
    api_keys: dict[str, str]      # integration API key -> tenant (from BEC_API_KEYS="tenant:key,tenant2:key2")

    @property
    def llm_mock(self) -> bool:
        return self.mock_mode or not self.nebius_api_key

    @property
    def tavily_mock(self) -> bool:
        return self.mock_mode or not self.tavily_api_key


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_settings() -> Settings:
    return Settings(
        nebius_api_key=_env("NEBIUS_API_KEY"),
        nebius_base_url=_env("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
        tavily_api_key=_env("TAVILY_API_KEY"),
        mock_mode=_env("MOCK_MODE", "true").lower() == "true",
        model_nano=_env("MODEL_NANO", "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B"),
        model_super=_env("MODEL_SUPER", "nvidia/nemotron-3-super-120b-a12b"),
        model_vl=_env("MODEL_VL", "nvidia/Nemotron-3.5-Super-VL"),
        model_ultra=_env("MODEL_ULTRA", "nvidia/Nemotron-3-Ultra-550b-a55b"),
        guardian_report_url=_env("GUARDIAN_REPORT_URL", "http://localhost:8000/api/guardian/report"),
        guardian_interval_minutes=int(_env("GUARDIAN_INTERVAL_MINUTES", "15")),
        api_keys=_parse_api_keys(_env("BEC_API_KEYS")),
    )


def _parse_api_keys(value: str) -> dict[str, str]:
    pairs = [item.split(":", 1) for item in value.split(",") if ":" in item]
    return {key.strip(): tenant.strip() for tenant, key in pairs if tenant.strip() and key.strip()}


def log_modes(s: Settings) -> None:
    log.warning("LLM (Token Factory): %s mode", "MOCK" if s.llm_mock else "REAL")
    log.warning("Tavily: %s mode", "MOCK" if s.tavily_mock else "REAL")
