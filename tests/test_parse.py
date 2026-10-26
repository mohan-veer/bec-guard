from app.phase_a.parse import parse_auth_results
from tests.helpers import load_scenario


def test_parse_headers_and_body():
    e = load_scenario("02_hacked_vendor_thread.eml")
    assert e.message_id == "<s02-thread@acmesupply.com>"
    assert e.in_reply_to == "<acm-10437-original@acmesupply.com>"
    assert e.from_name == "Sam Ortiz"
    assert e.from_addr == "ar@acmesupply.com"
    assert e.from_domain == "acmesupply.com"
    assert e.to == ["jordan.ellis@riverbenddental.com"]
    assert e.date is not None and e.date.year == 2026
    assert "Pacific Crest Bank" in e.body_text
    assert (e.spf, e.dkim, e.dmarc) == ("pass", "pass", "pass")


def test_domain_is_lowercased_so_capital_i_becomes_i():
    e = load_scenario("01_lookalike_vendor.eml")
    assert e.from_domain == "acmesuppiy.com"


def test_pdf_attachment_is_extracted():
    e = load_scenario("07_pdf_bank_details.eml")
    assert len(e.attachments) == 1
    a = e.attachments[0]
    assert a.filename == "ACM-10437-remittance.pdf"
    assert a.content_type == "application/pdf"
    assert a.data.startswith(b"%PDF")
    assert "Pacific Crest" not in e.body_text  # bank details only in the PDF


def test_auth_results_parsing():
    r = parse_auth_results("mx; spf=pass smtp.mailfrom=x.com; dkim=none; dmarc=FAIL header.from=x.com")
    assert r == {"spf": "pass", "dkim": "none", "dmarc": "fail"}
    assert parse_auth_results("") == {"spf": None, "dkim": None, "dmarc": None}


def test_reply_to_parsed():
    from app.phase_a.parse import parse_eml
    raw = b"Message-ID: <x@a.com>\nFrom: A <a@a.com>\nReply-To: b@evil.com\nSubject: s\n\nbody"
    e = parse_eml(raw)
    assert e.reply_to == "b@evil.com"
    assert e.spf is None


def test_html_only_body_is_converted_to_text():
    from app.phase_a.parse import parse_eml
    raw = (b"Message-ID: <x@a.com>\nFrom: a@a.com\nContent-Type: text/html\n\n"
           b"<p>Please pay <b>today</b></p>")
    assert parse_eml(raw).body_text.strip() == "Please pay today"
