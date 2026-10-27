# Where BEC Guard's records come from

BEC Guard compares every payment request with what your organization already knows: who your vendors are, which
bank account each one is paid to, which invoices you have paid, and who your staff are. The card shows these records
as evidence under the line they support ("your 6 paid Acme Supply invoices all went to account ending 4821", with the
invoices listed).

## Today (hackathon build): files per organization

Each organization (tenant) has its own folder, read only for that tenant's API key:

```
data/tenants/<tenant>/vendor_ledger.json    vendors, contacts, bank account on file, invoices
data/tenants/<tenant>/org_directory.json    staff and their phone numbers
```

The demo organization's files are generated with the demo mailbox history by `scripts/make_demo_data.py`, so the
invoices in the inbox and the invoices in the records always agree. All companies, people, bank accounts (routing
numbers start with 999) and phone numbers (555-01xx) are fictional.

### Vendor record (one entry of `vendors`)

```json
{
  "id": "acme",
  "name": "Acme Supply",
  "domains": [],
  "official_website": "",
  "official_phone": "(503) 555-0142",
  "contacts": [{"name": "Sam Ortiz", "email": "test.vendor26@yahoo.com", "role": "Accounts Receivable"}],
  "bank_account": {"bank_name": "First Cascade Bank", "routing_number": "999000111",
                   "account_last4": "4821", "account_holder": "Acme Supply LLC"},
  "payment_method": "ACH",
  "usual_amount": {"min": 12000, "max": 25000},
  "invoice_pattern": "^ACM-\\d{5}$",
  "remit_to": "1200 Industrial Way, Portland, OR 97210",
  "past_invoices": [
    {"number": "ACM-10436", "date": "2026-09-01", "amount": 19800.00, "po": "PO-2026-0111",
     "bank_last4": "4821", "method": "ACH", "status": "paid"}
  ],
  "past_emails": [{"from_addr": "test.vendor26@yahoo.com", "date": "2026-09-01", "subject": "Invoice ACM-10436",
                   "body": "..."}]
}
```

Only the last 4 digits of bank accounts are stored. `official_website` is optional: when it is set, BEC Guard also
cross-checks the phone number on the vendor's website; when it is empty, the number in your records is used.

### Staff record (one entry of `people`)

```json
{"name": "Dana Whitfield", "role": "CEO", "email": "dana.whitfield@riverbend.example", "phone": "(503) 555-0110"}
```

## In production: your accounting system and directory

The same two shapes would be filled from the systems an organization already uses, read-only:

| Record | Typical source | What BEC Guard reads |
|---|---|---|
| Vendors, bank account on file, payment method | QuickBooks Online (Vendor, Bill, BillPayment), Xero (Contacts, Bills, Payments), NetSuite | name, contacts, bank last 4, method |
| Paid and open invoices | the same accounting system | number, date, amount, status, account paid to |
| Staff and phone numbers | Google Workspace / Microsoft 365 directory, HR system | name, role, email, phone |
| Past emails for the writing-style check | the mailbox itself (already connected through the add-on) | the vendor's last few emails |

A small sync job (for example nightly, plus on demand) would map these into the JSON shapes above, so the checks and
the card stay the same. Bank details are never learned from email: an attacker who is already in a thread could
otherwise "teach" BEC Guard their account.
