from pathlib import Path

from app.phase_a.parse import parse_eml

SCENARIOS = Path(__file__).parent.parent / "scenarios"


def load_scenario(name: str):
    return parse_eml((SCENARIOS / name).read_bytes())


def codes(signals, verdict="unusual"):
    return {s.code for s in signals if s.verdict == verdict}
