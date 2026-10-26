"""Token Factory client. Every LLM call goes through complete_json().

Mock mode: returns the canned response for (step, key) from fixtures/llm/<step>.json, else its "_default".
Real mode: OpenAI SDK against Token Factory. We ask for JSON in the prompt (no vendor JSON mode: support varies
per model), validate with Pydantic, retry once with a reminder, then return the caller's safe default.
"""
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Awaitable, Callable, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import load_settings

FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "llm"
RETRY_MESSAGE = "Your last reply was not valid JSON for the requested format. Return only valid JSON, nothing else."

log = logging.getLogger("bec_guard.llm")
T = TypeVar("T", bound=BaseModel)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


@lru_cache
def _fixture(step: str) -> dict:
    return json.loads((FIXTURES / f"{step}.json").read_text())


def _mock(step: str, key: str, schema: type[T]) -> T:
    canned = _fixture(step)
    return schema.model_validate(canned.get(key, canned["_default"]))


@lru_cache
def _client() -> AsyncOpenAI:
    s = load_settings()
    # max_retries: the SDK retries 429 (honours Retry-After) and 5xx.
    return AsyncOpenAI(base_url=s.nebius_base_url, api_key=s.nebius_api_key, max_retries=2, timeout=60)


def _parse(text: str, schema: type[T]) -> T:
    """Strips reasoning blocks and code fences, then validates the outermost {...}."""
    text = _THINK_RE.sub("", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("no JSON object in reply")
    return schema.model_validate_json(text[start:end + 1])


async def _create(step: str, model: str, attempt: int, **kwargs):
    started = time.perf_counter()
    resp = await _client().chat.completions.create(model=model, temperature=0, **kwargs)
    usage = getattr(resp, "usage", None)
    log.info("llm step=%s model=%s attempt=%d latency_ms=%.0f tokens_in=%s tokens_out=%s", step, model, attempt,
             (time.perf_counter() - started) * 1000, getattr(usage, "prompt_tokens", "?"),
             getattr(usage, "completion_tokens", "?"))
    return resp.choices[0].message


async def complete_json(step: str, key: str, model: str, messages: list[dict], schema: type[T],
                        default: T | None = None, fallback_model: str | None = None) -> T:
    """step: fixture name (e.g. "gate0"); key: fixture lookup key (the email's Message-ID).
    default: returned if the real call fails or never yields valid JSON.
    fallback_model: tried if `model` errors (e.g. Ultra unavailable -> Super).
    """
    if load_settings().llm_mock:
        return _mock(step, key, schema)

    for m in [model] + ([fallback_model] if fallback_model else []):
        convo = list(messages)
        for attempt in (1, 2):
            try:
                text = (await _create(step, m, attempt, messages=convo)).content
            except Exception as exc:  # network, auth, 4xx/5xx after SDK retries
                log.error("llm step=%s model=%s failed: %s", step, m, exc)
                break
            try:
                return _parse(text, schema)
            except (ValueError, ValidationError) as exc:
                log.warning("llm step=%s attempt=%d invalid JSON: %s", step, attempt, exc)
                convo = convo + [{"role": "assistant", "content": text or ""}, {"role": "user", "content": RETRY_MESSAGE}]
        else:
            break  # model answered twice with invalid JSON: a fallback model would not help

    if default is None:
        raise RuntimeError(f"llm step {step} failed and no default was given")
    log.warning("llm step=%s using safe default", step)
    return default


# ---------- Tool-calling agent ----------

class AgentFailed(Exception):
    """The model gave no valid final answer (or does not do tool calls). Caller should fall back."""


FINAL_NOW = "Search limit reached. Give your final answer now as JSON only."
Handler = Callable[..., Awaitable[str]]


async def _dispatch(handlers: dict[str, Handler], name: str, args: dict) -> str:
    if name not in handlers:
        return f"Unknown tool: {name}"
    try:
        return await handlers[name](**args)
    except TypeError as exc:
        return f"Invalid arguments: {exc}"


async def run_tool_agent(step: str, key: str, model: str, messages: list[dict], tools: list[dict],
                         handlers: dict[str, Handler], schema: type[T], max_tool_calls: int) -> T:
    """The model decides which tools to call and when to stop. After max_tool_calls the next turn has no tools,
    forcing a final answer. Returns the final answer validated against schema, or raises AgentFailed.

    Mock mode: fixtures/llm/<step>.json[key]["turns"] scripts the model's turns
    ({"tool_calls": [{"name", "arguments"}]} or {"final": {...}}); tool handlers still run for real.
    """
    mock = load_settings().llm_mock
    script = iter(_fixture(step).get(key, _fixture(step)["_default"])["turns"]) if mock else None
    convo, calls, reminded = list(messages), 0, False

    for turn in range(1, max_tool_calls + 4):
        offer_tools = calls < max_tool_calls
        if mock:
            t = next(script, None)
            if t is None:
                raise AgentFailed("mock script ended without a final answer")
            tool_calls = [(f"m{turn}-{i}", c["name"], c["arguments"]) for i, c in enumerate(t.get("tool_calls", []))]
            content = json.dumps(t["final"]) if "final" in t else None
        else:
            try:
                msg = await _create(step, model, turn, messages=convo,
                                    **({"tools": tools, "tool_choice": "auto"} if offer_tools else {}))
            except Exception as exc:
                raise AgentFailed(f"API error: {exc}") from exc
            tool_calls = [(tc.id, tc.function.name, _loads(tc.function.arguments)) for tc in (msg.tool_calls or [])]
            content = msg.content

        if tool_calls and offer_tools:
            convo.append({"role": "assistant", "content": content or "",
                          "tool_calls": [{"id": i, "type": "function",
                                          "function": {"name": n, "arguments": json.dumps(a)}} for i, n, a in tool_calls]})
            for call_id, name, args in tool_calls:
                calls += 1
                result = await _dispatch(handlers, name, args) if calls <= max_tool_calls else FINAL_NOW
                convo.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": result})
            if calls >= max_tool_calls:
                convo.append({"role": "user", "content": FINAL_NOW})
            continue

        try:
            return _parse(content, schema)
        except (ValueError, ValidationError) as exc:
            if reminded:
                raise AgentFailed(f"no valid final answer: {exc}") from exc
            reminded = True
            convo += [{"role": "assistant", "content": content or ""}, {"role": "user", "content": RETRY_MESSAGE}]

    raise AgentFailed("turn limit reached")


def _loads(arguments: str) -> dict:
    try:
        value = json.loads(arguments or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}
