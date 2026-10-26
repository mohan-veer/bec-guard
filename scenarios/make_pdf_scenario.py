"""Builds 07_pdf_bank_details.eml: scenario 2, but the new bank account appears only in a PDF attachment.

Run once: python scenarios/make_pdf_scenario.py. Writes a minimal hand-made PDF (no PDF library needed).
"""
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).parent

PDF_LINES = [
    "ACME SUPPLY - UPDATED REMITTANCE INSTRUCTIONS",
    "Effective immediately for invoice ACM-10437 (PO-2026-0118)",
    "Amount: $18,400.00",
    "Bank: Pacific Crest Bank",
    "Routing number: 999000222",
    "Account number: 000058127731",
    "Account name: Acme Supply LLC",
    "Payment method: Wire transfer",
]


def make_pdf(lines: list[str]) -> bytes:
    text_ops = ["BT", "/F1 12 Tf", "16 TL", "72 720 Td"]
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        text_ops.append(f"({safe}) Tj T*")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def main() -> None:
    msg = EmailMessage()
    msg["Message-ID"] = "<s07-pdf@acmesupply.com>"
    msg["In-Reply-To"] = "<acm-10437-original@acmesupply.com>"
    msg["References"] = "<acm-10437-original@acmesupply.com>"
    msg["Date"] = "Tue, 20 Oct 2026 15:02:00 -0700"
    msg["From"] = "Sam Ortiz <ar@acmesupply.com>"
    msg["To"] = "Jordan Ellis <jordan.ellis@riverbenddental.com>"
    msg["Subject"] = "Re: Invoice ACM-10437"
    msg["Authentication-Results"] = (
        "mx.riverbenddental.com; spf=pass smtp.mailfrom=acmesupply.com; "
        "dkim=pass header.d=acmesupply.com; dmarc=pass header.from=acmesupply.com"
    )
    msg.set_content(
        "Hi Jordan,\n\n"
        "Please see the attached updated remittance details for ACM-10437 and use\n"
        "them for this payment.\n\n"
        "Thanks,\nSam Ortiz\nAccounts Receivable, Acme Supply\n"
    )
    msg.add_attachment(make_pdf(PDF_LINES), maintype="application", subtype="pdf",
                       filename="ACM-10437-remittance.pdf")
    (HERE / "07_pdf_bank_details.eml").write_bytes(bytes(msg))


if __name__ == "__main__":
    main()
