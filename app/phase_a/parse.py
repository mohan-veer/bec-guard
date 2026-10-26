""".eml bytes -> Email model (headers, body text, attachments)."""
import email
import email.policy
import html
import re

from app.phase_a.models import Attachment, Email

_AUTH_RE = re.compile(r"\b(spf|dkim|dmarc)=(\w+)", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_auth_results(header: str) -> dict[str, str | None]:
    found = {k.lower(): v.lower() for k, v in _AUTH_RE.findall(header or "")}
    return {k: found.get(k) for k in ("spf", "dkim", "dmarc")}


def _first_address(msg, name: str) -> tuple[str, str]:
    """Returns (display_name, lowercased address) of the first address in a header, or ("", "")."""
    header = msg[name]
    if not header or not header.addresses:
        return "", ""
    a = header.addresses[0]
    return a.display_name, a.addr_spec.lower()


def _body_text(msg) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    text = part.get_content()
    if part.get_content_type() == "text/html":
        text = html.unescape(_TAG_RE.sub("", text))
    return text


def parse_eml(raw: bytes) -> Email:
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    from_name, from_addr = _first_address(msg, "From")
    _, reply_to = _first_address(msg, "Reply-To")
    to = [a.addr_spec.lower() for a in msg["To"].addresses] if msg["To"] else []
    date = msg["Date"].datetime if msg["Date"] else None
    auth = parse_auth_results(str(msg.get("Authentication-Results", "")))
    attachments = [
        Attachment(filename=p.get_filename() or "attachment", content_type=p.get_content_type(),
                   data=p.get_payload(decode=True) or b"")
        for p in msg.iter_attachments()
    ]
    return Email(
        message_id=str(msg.get("Message-ID", "")).strip(),
        in_reply_to=str(msg["In-Reply-To"]).strip() if msg["In-Reply-To"] else None,
        subject=str(msg.get("Subject", "")),
        from_name=from_name,
        from_addr=from_addr,
        reply_to=reply_to or None,
        to=to,
        date=date,
        body_text=_body_text(msg),
        attachments=attachments,
        **auth,
    )
