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
| **Decision** | 🔴 **Verify before paying**: call Acme Supply at (503) 555-0142 (from your vendor records, not from this email) |

**A2. Lookalike domain (best effort)** — a "fake mailer" site sends as e.g. `ar@acmesuppIy.example`. Usually fails
SPF/DMARC and lands in Spam (the scanner reads Spam too); delivery isn't guaranteed. Only to our own test accounts,
never with a domain a real company owns. The lookalike-domain, domain-age and web-consensus (Nemotron Super + Tavily)
checks are always shown in the sample inbox on the website.

**A3. A stranger claims to be a real, well-known supplier** — from `testvendor.26@outlook.com`, display name
"Henry Schein Billing", asking to pay invoice HS-55120 ($6,480) within 3 days, with the scammer's own phone in the
signature. Uses a real company's name only in this private test sent to our own account (the call-back number shown
comes from that company's public website). Files: `demo-emails/A3-unknown-company/`.

| Check | Result |
|---|---|
| Org: web check (Nemotron Super agent + Tavily) | ❌ the agent finds Henry Schein's official site (henryschein.com); the email came from outlook.com |
| Org: phone cross-check | ❌ the email's number (206) 555-0177 isn't Henry Schein's number on henryschein.com |
| Entity: sender not on file, free email | ❌ |
| Entity: address resemblance | supporting fact only: "its address also resembles Sam Ortiz's address on file at Acme Supply" (the email claims another company, so Acme's invoices and amounts are not compared) |
| Content: language (Nemotron Super) | pressure ("within 3 days") |
| **Decision** | 🔴 **Verify before paying**: "This email says it's from Henry Schein, but it was sent from outlook.com, not Henry Schein's website (henryschein.com)… call Henry Schein at <number from henryschein.com>" |

Phone numbers on the card always come from a trusted source with its name attached: your vendor records, your
staff directory, or the company's official website found by the agent. A number written in the email is never
offered; it is compared with the trusted ones.

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
| **Decision** | 🔴 **Verify before paying**: bank details changed, call Acme on the number in your records |

**B1b. Same, but the new account is only in a PDF** — requires the real Nemotron Super VL model to read the PDF.

**B2. Our own mailbox is hacked** — we play the attacker in `testorganization26@gmail.com`: Gmail Settings → Filters
→ create a filter matching `invoice OR payment OR bank` with **Skip the Inbox** + **Mark as read** (optionally add
`testvendor.26@outlook.com` as a forwarding address and forward matches to it). Then BEC Guard → **Check mailbox
settings** → "Act now: hides payment emails / forwards mail outside". Same check runs daily on its own.

**B3. The computer is compromised** — Guardian local agent (Phase B): snapshot of startup items, scheduled tasks,
processes, compared with a baseline; Nemotron explains anything new. Uses harmless stand-in scripts only.

### Control: a normal invoice

From the real `test.vendor26@yahoo.com`: "Invoice ACM-10438, $17,200.00, PO-2026-0125, ACH to the usual account."
Expected: **no label**; the card says "No issues found" and lists what was checked.

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
