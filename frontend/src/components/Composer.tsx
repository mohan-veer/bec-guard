import { useState } from "react";
import { buildEml, TO, type ComposeFields, type Delivery } from "../compose";
import { PRESETS } from "../presets";
import Records from "./Records";

const MAX_PDF = 5 * 1024 * 1024; // arbitrary; keeps the request well under the 10 MB API limit

const input = "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-2 focus:outline-blue-200";

function readBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

interface Props {
  busy: boolean;
  onCheck: (eml: string, delivery: Delivery) => void;
}

export default function Composer({ busy, onCheck }: Props) {
  const [f, setF] = useState<ComposeFields>(PRESETS[0].fields);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [pdfInput, setPdfInput] = useState(0); // bumped to clear the file picker when an example replaces the form
  const set = (patch: Partial<ComposeFields>) => setF((old) => ({ ...old, ...patch }));
  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.fromAddr.trim()) && f.body.trim().length > 0;

  async function choosePdf(file: File | undefined) {
    setPdfError(null);
    if (!file) return set({ pdf: undefined });
    if (file.size > MAX_PDF) return setPdfError("That PDF is larger than 5 MB.");
    set({ pdf: { name: file.name, base64: await readBase64(file) } });
  }

  function download() {
    const url = URL.createObjectURL(new Blob([buildEml(f)], { type: "message/rfc822" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: "test-email.eml" });
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); // Safari needs the URL until the download starts
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
      <form
        className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
        onSubmit={(e) => { e.preventDefault(); if (valid) onCheck(buildEml(f), f.delivery); }}
      >
        <div>
          <h3 className="font-semibold">Write a test email to Jordan</h3>
          <p className="mt-1 text-sm text-slate-600">
            Nothing is sent. BEC Guard checks it as if it had just arrived in Jordan's Gmail. Pretend to be anyone:
            start from an example, then change it.
          </p>
          <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="Examples">
            {PRESETS.map((p) => (
              <button key={p.id} type="button" onClick={() => { setF(p.fields); setPdfError(null); setPdfInput((n) => n + 1); }}
                className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50">
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="font-medium">Sender name</span>
            <input className={`${input} mt-1`} value={f.fromName} onChange={(e) => set({ fromName: e.target.value })} maxLength={100} />
          </label>
          <label className="text-sm">
            <span className="font-medium">Sender address</span>
            <input className={`${input} mt-1 font-mono`} value={f.fromAddr} onChange={(e) => set({ fromAddr: e.target.value })}
              maxLength={254} required type="text" inputMode="email" spellCheck={false} />
          </label>
        </div>
        <div className="text-sm"><span className="font-medium">To</span> <span className="font-mono text-slate-600">{TO}</span></div>
        <label className="text-sm">
          <span className="font-medium">Subject</span>
          <input className={`${input} mt-1`} value={f.subject} onChange={(e) => set({ subject: e.target.value })} maxLength={200} />
        </label>
        <label className="text-sm">
          <span className="font-medium">Message</span>
          <textarea className={`${input} mt-1 min-h-48 font-sans`} value={f.body} onChange={(e) => set({ body: e.target.value })}
            maxLength={10000} required />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-sm">
            <span className="font-medium">PDF attachment (optional)</span>
            <input key={pdfInput} type="file" accept="application/pdf,.pdf" className="mt-1 block w-full text-sm"
              onChange={(e) => choosePdf(e.target.files?.[0])} />
            {f.pdf && <span className="mt-1 block text-xs text-slate-500">Attached: {f.pdf.name}</span>}
            {pdfError && <span role="alert" className="mt-1 block text-xs text-red-700">{pdfError}</span>}
          </label>
          <fieldset className="text-sm">
            <legend className="font-medium">How did it arrive? <span className="font-normal text-slate-500">(simulated)</span></legend>
            {([["pass", "Passed sender checks (SPF, DKIM, DMARC)"], ["fail", "Failed sender checks"]] as const).map(([v, label]) => (
              <label key={v} className="mt-1 flex items-center gap-2">
                <input type="radio" name="delivery" checked={f.delivery === v} onChange={() => set({ delivery: v as Delivery })} />
                {label}
              </label>
            ))}
            <p className="mt-1 text-xs text-slate-500">A hacked vendor mailbox passes these checks; a lookalike domain usually fails them.</p>
          </fieldset>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={!valid || busy}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-60">
            {busy ? "Checking…" : "Check this email"}
          </button>
          <button type="button" disabled={!valid} onClick={download}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60">
            Download .eml
          </button>
        </div>
      </form>

      <aside aria-label="Riverbend's records">
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Riverbend's records</h3>
        <Records />
      </aside>
    </div>
  );
}
