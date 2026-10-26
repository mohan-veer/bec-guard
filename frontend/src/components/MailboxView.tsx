import { useState } from "react";
import { checkMailbox } from "../api";
import type { MailboxFinding, MailboxReport } from "../types";

type Provider = "outlook" | "gmail";
const PROVIDERS: { id: Provider; label: string }[] = [
  { id: "gmail", label: "Gmail / Google Workspace" },
  { id: "outlook", label: "Outlook / Microsoft 365" },
];

function FindingCard({ f }: { f: MailboxFinding }) {
  const high = f.severity === "high";
  return (
    <li className={`rounded-xl border-2 bg-white p-5 ${high ? "border-amber-300" : "border-slate-200"}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${high ? "bg-amber-600 text-white" : "bg-slate-200 text-slate-700"}`}>
          {high ? "Act now" : "Review"}
        </span>
        <h3 className="font-mono text-sm font-semibold break-all">{f.rule_name}</h3>
      </div>
      <ul className="mt-3 flex flex-col gap-1 text-sm">
        {f.reasons.map((r) => (
          <li key={r} className="flex gap-2"><span aria-hidden className="text-amber-600">•</span><span>{r}</span></li>
        ))}
      </ul>
      {f.explanation && (
        <p className="mt-3 text-sm text-slate-600">
          {f.explanation} <span className="text-xs text-indigo-700">· Nemotron Super</span>
        </p>
      )}
      <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm font-medium">{f.next_step}</p>
    </li>
  );
}

export default function MailboxView() {
  const [provider, setProvider] = useState<Provider>("gmail");
  const [state, setState] = useState<{ status: "idle" | "loading" | "done" | "error"; report?: MailboxReport; error?: string }>({ status: "idle" });

  async function run(p: Provider) {
    setProvider(p);
    setState({ status: "loading" });
    try {
      setState({ status: "done", report: await checkMailbox(p) });
    } catch (err) {
      setState({ status: "error", error: (err as Error).message });
    }
  }

  const report = state.report;
  const highs = report?.findings.filter((f) => f.severity === "high").length ?? 0;
  const btn = "rounded-lg px-4 py-2 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 disabled:opacity-60";

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <h2 className="text-lg font-semibold">Has someone tampered with your mailbox?</h2>
        <p className="mt-1 text-sm text-slate-600">
          After a password is stolen, attackers often add hidden inbox rules or forwarding so they can read and hide
          payment emails. The BEC Guard add-on reads your rules and forwarding settings and never changes them.
          Try it here on a sample mailbox.
        </p>
        <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Sample mailbox">
          {PROVIDERS.map((p) => (
            <button key={p.id} type="button" disabled={state.status === "loading"} onClick={() => run(p.id)}
              aria-pressed={provider === p.id && state.status !== "idle"}
              className={`${btn} border border-slate-300 bg-white hover:bg-slate-50`}>
              Sample {p.label} mailbox
            </button>
          ))}
        </div>
      </section>

      <section aria-live="polite" aria-busy={state.status === "loading"} className="flex flex-col gap-4">
        {state.status === "loading" && <p className="text-sm text-slate-500">Reading rules and forwarding settings…</p>}
        {state.status === "error" && (
          <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
            <p>{state.error}</p>
            <button type="button" onClick={() => run(provider)} className="mt-3 rounded-md bg-white px-3 py-1.5 font-medium shadow-sm ring-1 ring-red-200">Try again</button>
          </div>
        )}
        {report && state.status === "done" && (
          <>
            <div className={`rounded-xl border-2 p-5 ${highs ? "border-amber-300 bg-amber-50" : report.findings.length ? "border-yellow-300 bg-yellow-50" : "border-emerald-300 bg-emerald-50"}`}>
              <h2 className="font-semibold">
                {highs ? `${highs} setting${highs > 1 ? "s" : ""} need${highs > 1 ? "" : "s"} action now`
                  : report.findings.length ? "Some settings are worth a look" : "No risky rules or forwarding found"}
              </h2>
              <p className="mt-1 text-sm text-slate-700">
                Checked {report.rules_checked} rule{report.rules_checked === 1 ? "" : "s"}
                {report.rules_disabled ? ` (${report.rules_disabled} turned off, skipped)` : ""} and forwarding settings.
                {report.source === "fixture" && " This is a sample mailbox."}
              </p>
            </div>
            {report.findings.length > 0 && (
              <ul className="flex flex-col gap-3">{report.findings.map((f) => <FindingCard key={f.id} f={f} />)}</ul>
            )}
            {report.notes.map((n) => <p key={n} className="text-sm text-slate-600">{n}</p>)}
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h3 className="text-sm font-semibold text-slate-700">What this check can't see</h3>
              <ul className="mt-2 flex list-disc flex-col gap-1 pl-5 text-sm text-slate-600">
                {report.limits.map((l) => <li key={l}>{l}</li>)}
              </ul>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
