import type { EmailView } from "../types";

function formatDate(iso: string | null) {
  return iso ? new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "";
}

export default function EmailPane({ email, loading }: { email: EmailView | null; loading: boolean }) {
  if (!email) {
    return (
      <section aria-label="Email" className="flex min-h-48 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500">
        {loading ? "Opening email…" : "Select an email from the inbox, or upload an .eml file."}
      </section>
    );
  }
  return (
    <section aria-label="Email" className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <header className="border-b border-slate-100 p-5">
        <h2 className="text-lg font-semibold">{email.subject || "(no subject)"}</h2>
        <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-slate-500">From</dt>
          <dd className="min-w-0 break-words">
            {email.from_name && <span className="font-medium">{email.from_name} </span>}
            {/* Monospace so lookalikes like a capital I vs l are visible */}
            <span className="font-mono text-slate-700">&lt;{email.from_addr}&gt;</span>
          </dd>
          {email.reply_to && (
            <>
              <dt className="text-slate-500">Reply-To</dt>
              <dd className="font-mono break-words text-slate-700">{email.reply_to}</dd>
            </>
          )}
          <dt className="text-slate-500">To</dt>
          <dd className="font-mono break-words text-slate-700">{email.to.join(", ")}</dd>
          <dt className="text-slate-500">Date</dt>
          <dd className="text-slate-700">{formatDate(email.date)}</dd>
        </dl>
        {email.attachments.length > 0 && (
          <ul aria-label="Attachments" className="mt-3 flex flex-wrap gap-2">
            {email.attachments.map((a) => (
              <li key={a.filename} className="rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-700">
                {a.filename} · {(a.size / 1024).toFixed(1)} KB
              </li>
            ))}
          </ul>
        )}
      </header>
      <div className="whitespace-pre-wrap break-words p-5 text-sm leading-relaxed text-slate-800">{email.body_text}</div>
    </section>
  );
}
