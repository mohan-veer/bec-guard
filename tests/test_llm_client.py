"""Real-mode LLM path, exercised with a fake OpenAI client (no network, no keys)."""
import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.clients import llm


class Out(BaseModel):
    intent: str
    score: int


class FakeCompletions:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")

    def install(*replies):
        comp = FakeCompletions(replies)
        monkeypatch.setattr(llm, "_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=comp)))
        return comp
    return install


def run(default=None):
    return asyncio.run(llm.complete_json("gate0", "k", "some/model", [{"role": "user", "content": "hi"}], Out,
                                         default=default or Out(intent="fallback", score=0)))


def test_valid_json(fake):
    comp = fake('{"intent": "x", "score": 3}')
    assert run() == Out(intent="x", score=3)
    assert comp.calls[0]["model"] == "some/model"
    assert comp.calls[0]["temperature"] == 0


def test_strips_think_block_and_code_fence(fake):
    fake('<think>reasoning {not json}</think>\n```json\n{"intent": "x", "score": 1}\n```')
    assert run().score == 1


def test_retries_once_with_valid_json_reminder(fake):
    comp = fake("sorry, here you go: intent x", '{"intent": "x", "score": 2}')
    assert run().score == 2
    assert len(comp.calls) == 2
    assert "only valid JSON" in comp.calls[1]["messages"][-1]["content"]


def test_schema_violation_counts_as_parse_failure(fake):
    comp = fake('{"intent": "x", "score": "high"}', '{"intent": "x", "score": 4}')
    assert run().score == 4 and len(comp.calls) == 2


def test_two_failures_return_safe_default(fake):
    fake("nope", "still nope")
    assert run().intent == "fallback"


def test_api_error_returns_safe_default(fake):
    fake(RuntimeError("connection reset"))
    assert run().intent == "fallback"


class IntentOnly(BaseModel):
    intent: str


def test_mock_mode_never_calls_client(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setattr(llm, "_client", lambda: pytest.fail("client must not be used in mock mode"))
    out = asyncio.run(llm.complete_json("gate0", "<s03-giftcards@mail.gmail.com>", "m", [], IntentOnly))
    assert out.intent == "gift_cards"
