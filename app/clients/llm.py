"""Token Factory client. Every LLM call goes through complete_json().

Mock mode: returns the canned response for (step, key) from fixtures/llm/<step>.json, else its "_default".
Real mode: added in Phase 5.
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.config import load_settings

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "llm"

T = TypeVar("T", bound=BaseModel)


@lru_cache
def _fixture(step: str) -> dict:
    return json.loads((FIXTURES / f"{step}.json").read_text())


def _mock(step: str, key: str, schema: type[T]) -> T:
    canned = _fixture(step)
    return schema.model_validate(canned.get(key, canned["_default"]))


async def complete_json(step: str, key: str, model: str, messages: list[dict], schema: type[T]) -> T:
    """step: fixture name (e.g. "gate0"); key: fixture lookup key (the email's Message-ID)."""
    if load_settings().llm_mock:
        return _mock(step, key, schema)
    raise NotImplementedError("Real Token Factory calls arrive in Phase 5")
