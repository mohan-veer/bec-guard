# Manual test cases

These are the tests we ran by hand against BEC Guard, in real Gmail and on the website. The demo video shows a few of
them; all of them are here so you can see what was tested and repeat any of it.

Each folder is one test: `email.txt` (sender, recipient, subject, the expected result, and the body to copy), the
PDF to attach where there is one, or `steps.txt` when the test is a set of actions rather than one email.

**Nothing here is hard-coded.** These are inputs. No name, address, amount or account number from these emails
appears in the application code. BEC Guard compares each email with the organization's records
([data/tenants/riverbend/](../data/tenants/riverbend/)) and with what Nemotron and the web search find. The Gmail tests ran
with the real Nemotron models on Nebius Token Factory and real Tavily web search. (Mock mode, used when no keys are
set, replays saved model answers for the website's 7 sample-inbox emails only.)

## Who's who

All companies, people and bank accounts are fictional; the mailboxes are our own test accounts.

| Role | Mailbox |
|---|---|
| Jordan, accounts payable at Riverbend Dental (BEC Guard installed) | `testorganization26@gmail.com` |
| Sam, the real vendor at Acme Supply | `test.vendor26@yahoo.com` |
| The scammer | `testvendor.26@outlook.com` |
| Compliance contact (receives takeover alerts) | `markjrcompliance@gmail.com` |

## Tests and results

| Test | What it checks | Where run | Result |
|---|---|---|---|
| [C1_normal-invoice](C1_normal-invoice/) | A normal Acme invoice, paid to the usual account: no false alarm | Gmail | ✅ No label, "No issues found" |
| [A1_fake-vendor-new-bank-account](A1_fake-vendor-new-bank-account/) | A scammer uses Sam's name from a different address, new bank account, ACH → wire | Gmail | ✅ Verify before paying |
| [A3_stranger-claims-known-supplier](A3_stranger-claims-known-supplier/) | A stranger claims to be a well-known supplier; the agent finds the official website and phone | Gmail | ✅ Verify before paying (web check: official site differs from the sender's address; the email's phone isn't the company's) |
| [B1_hacked-vendor-changes-bank](B1_hacked-vendor-changes-bank/) | Sam's real mailbox is hacked: sender checks pass, bank account changes | Gmail | ✅ Verify before paying (new account vs the 6 paid invoices) |
| [B1b_hacked-vendor-bank-in-pdf](B1b_hacked-vendor-bank-in-pdf/) | Same, but the new account is only inside the PDF | Gmail | ✅ Verify before paying (Nemotron Super VL read the PDF) |
| [B2_hidden-inbox-filter](B2_hidden-inbox-filter/) | Our own mailbox is hacked: a filter hides payment emails | Gmail | ✅ Banner in BEC Guard + one email to compliance |
| [B2b_intruder-sends-bank-details](B2b_intruder-sends-bank-details/) | An intruder sends new bank details from our mailbox, then deletes the sent email | Gmail | ✅ Banner + one compliance email per event |
| [W1_website-upload-known-name-from-gmail](W1_website-upload-known-name-from-gmail/) | Upload an .eml: Acme's account manager's name from a personal Gmail address | Website (Try it) | ✅ Verify before paying |
| [W2_website-write-pacific-paper-invoice](W2_website-write-pacific-paper-invoice/) | Write an email three ways: hacked real address, lookalike address, normal invoice | Website (Try it) | ✅ Verify / Verify / No issues found |

Gmail tests were run on 2026-10-27 and 2026-10-28; website tests on 2026-10-29 (mock mode). Not run: a lookalike
domain delivered to Gmail (needs a domain we own; the website's sample inbox and W2 cover the lookalike check).
