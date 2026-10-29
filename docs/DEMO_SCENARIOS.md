# BEC Guard: demo dataset and scenarios

This is the setup we use to show BEC Guard working inside a real Gmail mailbox, and what each check does in each
scenario. The plan is fixed; change it only by updating this file.

## The cast

| Role | Who | Mailbox |
|---|---|---|
| Organization (AP clerk) | Jordan Ellis, Riverbend Dental Partners (fictional) | `testorganization26@gmail.com` (our test account, BEC Guard add-on installed) |
| Trusted vendor | Sam Ortiz, Acme Supply (fictional) | `test.vendor26@yahoo.com` (our test account) |
| Scammer | pretends to be Sam (and later the CEO) | `testvendor.26@outlook.com` (our test account; same username — dots ignored — different provider) |
| Colleagues, other vendors, newsletters | fictional | reserved `.example` domains (never deliverable, owned by no one) |

All people, companies, bank accounts (routing numbers start with `999`) and phone numbers (`555-01xx`) are fictional.

## Where the "truth" comes from

- **Vendor records** (`data/tenants/riverbend/vendor_ledger.json`): Acme's bank account on file (First Cascade Bank,
  account ending **4821**, ACH), usual invoice range ($12k–$25k), invoice numbering, PO numbers, and seven past
  invoices (six paid to 4821, **ACM-10437 still open**). In production this is the accounting system (QuickBooks,
  Xero); here it is a local file. BEC Guard never learns bank details from email, because an attacker who was already
  in a thread would poison that history.
- **Org directory** (`data/tenants/riverbend/org_directory.json`): staff and their phone numbers on file (the
  call-back numbers for internal requests).
- **Mailbox history** (below): what Jordan's inbox looked like before the attack. Past vendor emails are also used
  for the writing-style comparison.

Mailbox history and vendor records are generated from one definition (`scripts/make_demo_data.py`) and a test checks
they agree: every invoice PDF in the inbox matches an invoice in the records (number, amount, PO, account ending 4821).

## The mailbox history: 22 emails, June to October 2026

Imported into the organization mailbox with their original dates (`seedDemoHistory()` in the add-on). This is
simulated history, not delivered mail: every message carries the header `X-BEC-Guard-Demo: seeded-history`.

**Acme Supply: 5 conversations, 3 invoices**

| Date | Conversation | Attachment |
|---|---|---|
| Jun 10 | Vendor setup: "we're paid by ACH to the account ending 4821" + Jordan's reply | Vendor information sheet (PDF) |
| Jul 1 | Invoice ACM-10435 ($16,450) → "Paid today via ACH" | Invoice PDF |
| Aug 18 | Delivery schedule moves to Tuesdays → "Noted" | |
| Sep 1 | Invoice ACM-10436 ($19,800) → "Paid via ACH today" | Invoice PDF |
| Oct 1 | Invoice **ACM-10437 ($18,400)** → "Scheduled for our October 30 payment run" | Invoice PDF |

**Everyday mail (so the inbox looks lived-in)**: CEO's June update and team lunch; CFO's Q3 budget reminder
("Acme is our biggest line; flag anything unusual"); HR open enrollment; front-desk coverage request; Pacific Paper
and BrightClean invoices; Summit IT maintenance notice; DentalDesk schedule summaries; Pacific Dental Digest
newsletters (one about payment scams).

The scanner only checks mail that arrives after it was turned on, so the history is never labelled.

## Live scenarios (real emails, sent by hand during the demo)

### Scenario A: the email is not from our trusted vendor (impersonation)

**A1. Scammer pretends to be Sam** — from `testvendor.26@outlook.com`, display name "Sam Ortiz":
> Subject: Invoice ACM-10437 - urgent
> Hi Jordan, our bank flagged the ACH for ACM-10437. Please send the $18,400.00 today by wire to our new account:
> Bank: Lakeshore Commerce Bank / Routing: 999000666 / Account: 000044019055. Thanks, Sam

| Check | Result |
|---|---|
| Entity: address lookalike | ❌ same username as Acme's address on file (`test.vendor26@yahoo.com`), different provider |
| Entity: known name, new address | ❌ "Sam Ortiz" but not from Sam's address |
| Entity: first contact | ❌ no history with this sender |
| Entity: free email address | ❌ outlook.com, and this sender isn't on file |
| Content: bank details vs records | ❌ new account ending 9055 (on file: 4821, used on 6 invoices); ACH → wire |
| Content: language (Nemotron Super) | urgency ("today") |
| **Decision** | 🔴 **Verify before paying** — "Before paying, confirm the new bank details with Acme Supply at (503) 555-0142 (from your vendor records)"; the sender line shows the contact on file and their past emails |

**A2. Lookalike domain (best effort)** — a "fake mailer" site sends as e.g. `ar@acmesuppIy.example`. Usually fails
SPF/DMARC and lands in Spam (the scanner reads Spam too); delivery isn't guaranteed. Only to our own test accounts,
never with a domain a real company owns. The lookalike-domain, domain-age and web-consensus (Nemotron Super + Tavily)
checks are always shown in the sample inbox on the website.

**A3. A stranger claims to be a real, well-known supplier** — from `testvendor.26@outlook.com`, display name
"Henry Schein Billing", asking to pay invoice HS-55120 ($6,480) within 3 days, with the scammer's own phone in the
signature. Uses a real company's name only in this private test sent to our own account (the call-back number shown
comes from that company's public website). Files: `demo-emails/A3_stranger-claims-known-supplier/`.

| Check | Result |
|---|---|
| Org: web check (Nemotron Super agent + Tavily) | ❌ the agent finds Henry Schein's official site (henryschein.com); the email came from outlook.com |
| Org: phone cross-check | ❌ the email's number (206) 555-0177 isn't Henry Schein's number on henryschein.com |
| Entity: sender not on file, free email | ❌ |
| Entity: address resemblance | supporting fact only: "its address also resembles Sam Ortiz's address on file at Acme Supply" (the email claims another company, so Acme's invoices and amounts are not compared) |
| Content: language (Nemotron Super) | pressure ("within 3 days") |
| **Decision** | 🔴 **Verify before paying** — no call line (no relationship with Henry Schein); The company: "Says it's Henry Schein, but Henry Schein's website is henryschein.com and this came from outlook.com" with a source link to the page the agent used; The request: the email's phone vs the website's phone, payment to an account with no record |

Phone numbers on the card always come from a trusted source with its name attached: your vendor records, your
staff directory, or the company's official website found by the agent. A number written in the email is never
offered; it is compared with the trusted ones.

**A4. A stranger claims to be a new supplier (made-up company, safe for the video)** — same as A3, but "Quillbrook
Dental Supply" (fictional; the web search finds no real company by that name) sends its "first invoice" QDS-30418
($4,950, PDF) to an account with no record. Expected: 🔴 **Verify before paying** (rule `new_payee`: any payment to a
bank account with no record is confirmed before the first payment). Files: `demo-emails/A4_stranger-claims-new-supplier/`.

### Scenario B: an account is hacked

**B1. The vendor's real mailbox is hacked** — from the real `test.vendor26@yahoo.com`:
> Subject: Re: Invoice ACM-10437
> Hi Jordan, quick update: we moved our banking. Please use our new account for ACM-10437 ($18,400.00):
> Bank: Pacific Crest Bank / Routing: 999000222 / Account: 000058127731. Please process today, by wire.
> Thanks, Sam

| Check | Result |
|---|---|
| Entity: sender on file, SPF/DKIM/DMARC | ✅ really Sam's address (this is why sender checks alone fail against account takeover) |
| Content: bank details vs records | ❌ new account ending 7731 (on file: 4821, used on 6 invoices); ACH → wire |
| Content: language / writing style (Nemotron Super) | time pressure; style compared with Sam's past invoice emails |
| **Decision** | 🔴 **Verify before paying** — The sender ✓ and The company ✓, The request ⚠: the new account with the 3 latest paid invoices (all ••••4821) listed as evidence; "confirm the new bank details with Acme Supply at (503) 555-0142 (from your vendor records)" |

**B1b. Same, but the new account is only in a PDF** — requires the real Nemotron Super VL model to read the PDF.

**B2. Our own mailbox is hacked** — we play the attacker in `testorganization26@gmail.com`: Gmail Settings → Filters
→ create a filter matching `invoice OR payment OR bank` with **Skip the Inbox** + **Mark as read** (optionally add
`testvendor.26@outlook.com` as a forwarding address and forward matches to it). Then BEC Guard → **Check mailbox
settings** → "Act now: hides payment emails / forwards mail outside".

BEC Guard re-checks the settings and reads Gmail's change history every minute. A new filter, forwarding or
"send mail as" address is marked **NEW**; so is an email sent outside with bank details, a sent email that doesn't read
like Jordan, a sent email deleted soon after sending, or a payment email deleted. A red banner appears at the top of
every BEC Guard card ("This was me" clears it), and serious warnings are emailed once to the compliance contact on file
(`data/tenants/riverbend/security.json`, which the mailbox can't change). Outside office hours, everything is raised to
"Act now".

**B2b. The intruder sends from our mailbox** — from `testorganization26@gmail.com`, send Sam
(`test.vendor26@yahoo.com`) "our remittance details have been updated" with new bank details, then delete it from Sent.
Expected within ~1 minute: banner "Your mailbox may be in someone else's hands" (bank details sent outside; deleted
soon after sending; writing style unlike Jordan's) and one or two emails to the compliance contact.
Files: `demo-emails/B2_hidden-inbox-filter/steps.txt` (the filter) and `demo-emails/B2b_intruder-sends-bank-details/email.txt`.

### Control: a normal invoice

From the real `test.vendor26@yahoo.com`: "Invoice ACM-10438, $17,200.00, PO-2026-0125, ACH to the usual account."
Expected: **no label**; the card says "No issues found" and lists what was checked.

## How the card reads

"Verify before paying" (or "Looks unusual" / "No issues found"), one intro line, a call line only when a vendor or
colleague on file is involved (number from your records), then three sections — **The sender**, **The company**,
**The request** — with ⚠ what looks wrong, ℹ neutral facts, ✓ what checks out. Lines based on the web link to the page
that supported them; lines based on your records show those records (e.g. the last paid invoices). Nemotron Ultra
rewords the warnings in plain language; code rejects any rewrite that changes an address or a number.

## Running it

1. Organization mailbox: BEC Guard add-on installed and connected (see `gmail-addon/README.md`).
2. Script editor → run `seedDemoHistory` once (re-running is safe). `removeDemoHistory` moves it all to Trash.
3. Send the live emails above, wait 1–2 minutes, refresh Gmail: labels appear on risky mail; open one to see the card.

## What is real and what is simulated

| | |
|---|---|
| Real | Gmail delivery of the live emails (and Gmail's own SPF/DKIM/DMARC results), the add-on, the scanner, labels, the API, every rule check, the decision |
| Simulated | The mailbox history (imported, marked), the vendor records (local file instead of an accounting system), all companies and people |
| Real once model keys are set | Nemotron Nano / Super / Super VL / Ultra on Nebius Token Factory, Tavily web search |
