"""Result card for a non-technical reader: the decision, one line on why, then three sections — The sender, The
company, The request — each listing what looks wrong first, then neutral facts, then what checks out.

Facts come from the checks (rules, Nemotron, Tavily). Nemotron Ultra (fallback Super) only rewords each line in plain
language; a rewritten line is used only if it keeps every address, number and amount exactly (else the rule wording
stays), so a model can never put an invented number on the card. A call-back line appears only when there is a real
relationship (a vendor or colleague on file) and its number comes from your records, never from the email or a model.
"""
import re

from pydantic import BaseModel

from app.clients.llm import complete_json
from app.config import load_settings
from app.phase_a.models import AnalysisResult, Decision, Email, Signal

HEADLINES = {
    Decision.VERIFY_BEFORE_PAYING: "Verify before paying",
    Decision.LOOKS_UNUSUAL: "Looks unusual",
    Decision.NO_ISSUES_FOUND: "No issues found",
    None: "No money or data request found",
}
INTROS = {
    Decision.VERIFY_BEFORE_PAYING: "We found the following reasons this email may not be genuine:",
    Decision.LOOKS_UNUSUAL: "Some things in this email look unusual:",
    Decision.NO_ISSUES_FOUND: "No warning signs in these checks:",
    None: "This email doesn't ask for money or data.",
}
SECTIONS = ["The sender", "The company", "The request"]
_GROUP_SECTION = {"entity": "The sender", "org": "The company", "content": "The request"}
_CODE_SECTION = {"email_phone_mismatch": "The request", "email_phone_matches": "The request"}
_NOT_SHOWN = {"intent", "callback_number"}
# Neutral facts: neither a warning nor reassurance.
NOTE_CODES = {"email_auth_unverified_sender", "web_consensus_other_domain", "web_consensus_unknown", "domain_age_unknown",
              "phones_differ"}
CALLBACK_PRIORITY = {"directory": 0, "records": 1, "web": 2}  # most trustworthy number first
_WEIGHT_ORDER = {"strong": 0, "medium": 1, "low": 2, "none": 3}
# Within the same weight: independently verified facts first; "not in your records" last (new contacts happen).
_ORDER_AMONG_EQUALS = {"web_consensus_mismatch": 0, "email_phone_mismatch": 1, "first_contact": 99}
# The sender section reads as a story, whatever the weights: the name vs the address, then the address vs the one
# on file, then the rest, and "not in your records" last.
_SENDER_ORDER = {"display_name_mismatch": 0, "known_name_new_address": 0, "address_lookalike": 1, "first_contact": 99}


class Item(BaseModel):
    tone: str                     # warn | note | ok
    text: str
    code: str
    sources: list[dict] = []      # [{"title", "url"}]: the web pages that supported this line (real web results only)


class Section(BaseModel):
    title: str
    items: list[Item]


class Card(BaseModel):
    message_id: str
    decision: Decision | None
    rule: str | None
    intent: str
    headline: str
    intro: str
    action: str                   # call-back line, only when a vendor/colleague on file is involved; else ""
    explanation: str | None       # kept for API compatibility (no longer generated)
    sections: list[Section]
    looks_fine: list[str]
    looks_unusual: list[str]
    notes: list[str]
    callback: dict | None         # the first trusted number
    callbacks: list[dict]         # every trusted number with its source (records, directory, official website)
    checks: list[Signal]          # the "How this was checked" panel


# ---------- plain-language wording (Nemotron Ultra, checked by code) ----------

WORDING_SYSTEM = (
    "You rewrite the lines of a warning card for an accounts-payable clerk who is not technical. For each line, write "
    "ONE short, plain sentence (at most 25 words) that says the same thing. Rules: use everyday words; never use "
    "technical terms such as domain, provider, server, header, SPF, DKIM, DMARC or lookalike (say 'web address' or "
    "'email service' if needed); when two things differ, show both clearly, never say 'almost the same' or 'similar'; "
    "keep every email address, web address, phone number, amount, account number and invoice number exactly as "
    "written; do not add facts, advice or instructions; never say 'safe' or 'fraud'. "
    'Reply with JSON only: {"lines": [{"id": "<same id>", "text": "<rewritten line>"}]}.'
)
_VALUE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\$[\d,]+(?:\.\d+)?|\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}"
                    r"|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|co|io|example|ai)\b|\d+", re.IGNORECASE)
_JARGON = re.compile(r"\b(domain|provider|server|header|spf|dkim|dmarc|lookalike)s?\b", re.IGNORECASE)
MAX_WORDS = 32


class _Line(BaseModel):
    id: str
    text: str


class _WordingOut(BaseModel):
    lines: list[_Line] = []


def accept_rewrite(original: str, rewritten: str) -> bool:
    """A rewritten line may only reuse values from the original line (no invented or changed numbers/addresses)."""
    if not rewritten or len(rewritten.split()) > MAX_WORDS or _JARGON.search(rewritten):
        return False
    norm = lambda v: re.sub(r"[^\w@.$]", "", v.lower())  # noqa: E731  "(631) 843-5500" == "631-843-5500"
    allowed = {norm(v) for v in _VALUE.findall(original)}
    return all(norm(v) in allowed for v in _VALUE.findall(rewritten))


async def word_signals(signals: list[Signal], key: str) -> dict[int, str]:
    """Index of signal -> plain rewrite for warnings and notes. Lines failing accept_rewrite keep the rule wording.
    "What checks out" lines are never reworded: reassurance must stay exactly as precise as the check behind it
    (a rewrite once turned "doesn't imitate any company you work with" into "doesn't match any company")."""
    shown = {i: s for i, s in enumerate(signals)
             if s.code not in _NOT_SHOWN and (s.verdict == "unusual" or s.code in NOTE_CODES)}
    if not shown:
        return {}
    lines = "\n".join(f'{{"id": "{i}", "text": {s.message!r}}}' for i, s in shown.items())
    st = load_settings()
    out = await complete_json(
        step="card_wording", key=key, model=st.model_ultra, fallback_model=st.model_super,
        messages=[{"role": "system", "content": WORDING_SYSTEM}, {"role": "user", "content": f"Lines:\n{lines}"}],
        schema=_WordingOut, default=_WordingOut(),
    )
    worded = {}
    for line in out.lines:
        if line.id.isdigit() and int(line.id) in shown and accept_rewrite(shown[int(line.id)].message, line.text):
            worded[int(line.id)] = line.text.strip()
    return worded


# ---------- card ----------

def _action(r: AnalysisResult, callbacks: list[dict]) -> str:
    """Only when a vendor or colleague on file is involved: confirm with them on the number from your records."""
    if r.decision in (None, Decision.NO_ISSUES_FOUND):
        return ""
    cb = next((c for c in callbacks if c.get("kind") in ("records", "directory")), None)
    if not cb:
        return ""
    where = "your vendor records" if cb["kind"] == "records" else "your staff directory"
    new_account = any(s.code == "bank_change" and s.verdict == "unusual" for s in r.signals)
    what = "Before paying, confirm the new bank details with" if new_account else "Before acting, confirm with"
    return f"{what} {cb['name']} at {cb['phone']} (from {where}), not a number from this email."


def _tone(s: Signal) -> str | None:
    if s.verdict == "unusual":
        return "warn"
    if s.verdict == "fine":
        return "ok"
    return "note" if s.code in NOTE_CODES else None


def _sort_key(s: Signal):
    tone_rank = {"warn": 0, "note": 1, "ok": 2}[_tone(s)]
    if s.group == "entity":
        return tone_rank, _SENDER_ORDER.get(s.code, 50), _WEIGHT_ORDER[s.weight]
    return tone_rank, _WEIGHT_ORDER[s.weight], _ORDER_AMONG_EQUALS.get(s.code, 9)


def build_card(r: AnalysisResult, e: Email) -> Card:
    callbacks = sorted((s.data for s in r.signals if s.code == "callback_number"),
                       key=lambda c: CALLBACK_PRIORITY.get(c.get("kind"), 9))
    text = {id(s): r.wording.get(i, s.message) for i, s in enumerate(r.signals)}
    shown = [s for s in r.signals if s.code not in _NOT_SHOWN and _tone(s)]
    sections = []
    for title in SECTIONS:
        in_section = sorted((s for s in shown if _CODE_SECTION.get(s.code, _GROUP_SECTION.get(s.group)) == title),
                            key=_sort_key)
        if in_section:
            sections.append(Section(title=title, items=[Item(tone=_tone(s), text=text[id(s)], code=s.code,
                                                             sources=s.data.get("sources", [])) for s in in_section]))
    return Card(
        message_id=r.message_id, decision=r.decision, rule=r.rule, intent=r.intent.value,
        headline=HEADLINES[r.decision], intro=INTROS[r.decision], action=_action(r, callbacks), explanation=None,
        sections=sections,
        looks_fine=[i.text for sec in sections for i in sec.items if i.tone == "ok"],
        looks_unusual=[i.text for sec in sections for i in sec.items if i.tone == "warn"],  # in card order
        notes=[i.text for sec in sections for i in sec.items if i.tone == "note"],
        callback=callbacks[0] if callbacks else None, callbacks=callbacks, checks=r.signals,
    )
