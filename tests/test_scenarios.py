"""All 7 demo scenarios in MOCK_MODE must reach the expected decision for the expected reason."""
import asyncio
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SPEC = json.loads((ROOT / "scenarios/expected.json").read_text())["scenarios"]


@pytest.fixture(autouse=True)
def _mock_mode(monkeypatch):
    monkeypatch.setenv("MOCK_MODE", "true")


@pytest.mark.parametrize("case", SPEC, ids=[s["file"] for s in SPEC])
def test_scenario(case):
    from app.phase_a.pipeline import analyze_eml  # not built yet: Phase 3–6

    result = asyncio.run(analyze_eml((ROOT / "scenarios" / case["file"]).read_bytes()))

    assert result.intent.value == case["intent"]
    assert result.decision.value in case["decisions"]
    fired = {s.code for s in result.signals if s.verdict == "unusual"}
    for code in case["key_signals"]:
        assert code in fired, f"{code} did not fire; fired={sorted(fired)}"
