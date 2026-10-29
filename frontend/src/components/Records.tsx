import { useEffect, useState } from "react";
import { fetchRecords } from "../api";
import type { SampleRecords } from "../types";

const money = (v: number | string) => Number(v).toLocaleString("en-US", { style: "currency", currency: "USD" });

/** What Riverbend's records say (fictional), so visitors know who to impersonate and what "normal" looks like. */
export default function Records() {
  const [records, setRecords] = useState<SampleRecords | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => { fetchRecords().then(setRecords).catch(() => setError(true)); }, []);

  if (error) return <p className="text-sm text-red-700">Could not load the sample records.</p>;
  if (!records) return <p className="text-sm text-slate-500">Loading records…</p>;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <p className="text-slate-600">
        BEC Guard compares each email with these records. In a real company they come from the accounting system.
      </p>
      {records.vendors.map((v) => (
        <details key={v.name} className="rounded-lg border border-slate-200 bg-white p-3" open={v.name === "Acme Supply"}>
          <summary className="cursor-pointer font-medium">
            {v.name} <span className="font-normal text-slate-500">· vendor</span>
          </summary>
          <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
            <dt className="text-slate-500">Contacts</dt>
            <dd>{v.contacts.map((c) => <div key={c.email}>{c.name}, {c.role} <span className="font-mono text-xs">{c.email}</span></div>)}</dd>
            <dt className="text-slate-500">Paid to</dt>
            <dd>{v.bank_account.bank_name}, account ending {v.bank_account.account_last4}, by {v.payment_method}</dd>
            <dt className="text-slate-500">Usual invoice</dt>
            <dd>{money(v.usual_amount.min)} – {money(v.usual_amount.max)}</dd>
            <dt className="text-slate-500">Phone</dt>
            <dd>{v.official_phone}</dd>
          </dl>
          {v.past_invoices.length > 0 && (
            <table className="mt-3 w-full text-left text-xs">
              <thead className="text-slate-500"><tr><th className="font-medium">Invoice</th><th className="font-medium">Amount</th><th className="font-medium">Paid to</th><th className="font-medium">Status</th></tr></thead>
              <tbody>
                {v.past_invoices.slice(-4).map((i) => (
                  <tr key={i.number}><td className="font-mono">{i.number}</td><td>{money(i.amount)}</td><td>••••{i.bank_last4}</td><td>{i.status}</td></tr>
                ))}
              </tbody>
            </table>
          )}
          {v.past_emails.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-slate-500">Past emails ({v.past_emails.length}), used for the writing-style check</div>
              {v.past_emails.slice(-2).map((m) => (
                <details key={m.date + m.subject} className="mt-1">
                  <summary className="cursor-pointer text-xs">{m.date} · {m.subject}</summary>
                  <pre className="mt-1 whitespace-pre-wrap rounded bg-slate-50 p-2 font-sans text-xs text-slate-700">{m.body}</pre>
                </details>
              ))}
            </div>
          )}
        </details>
      ))}
      <details className="rounded-lg border border-slate-200 bg-white p-3">
        <summary className="cursor-pointer font-medium">{records.org.org_name} <span className="font-normal text-slate-500">· staff</span></summary>
        <ul className="mt-2 flex flex-col gap-1">
          {records.org.people.map((p) => (
            <li key={p.email}>{p.name}, {p.role} <span className="font-mono text-xs">{p.email}</span></li>
          ))}
        </ul>
      </details>
    </div>
  );
}
