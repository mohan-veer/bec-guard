import { useRef } from "react";
import type { ScenarioItem } from "../types";

const MAX_UPLOAD = 10 * 1024 * 1024; // matches the API limit

interface Props {
  scenarios: ScenarioItem[] | null;
  loadError: string | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onUpload: (file: File) => void;
  onUploadError: (message: string) => void;
}

export default function Inbox({ scenarios, loadError, selectedId, onSelect, onUpload, onUploadError }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);

  function handleFile(file: File | undefined) {
    if (!file) return;
    if (file.size > MAX_UPLOAD) onUploadError("That file is larger than 10 MB.");
    else onUpload(file);
    if (fileInput.current) fileInput.current.value = "";
  }

  return (
    <nav aria-label="Inbox" className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Inbox</h2>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
        >
          Upload .eml
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".eml,message/rfc822"
          className="sr-only"
          aria-label="Upload an .eml file"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
      </div>

      {loadError && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-800">{loadError}</p>}
      {!scenarios && !loadError && <p className="text-sm text-slate-500">Loading emails…</p>}
      {scenarios?.length === 0 && <p className="text-sm text-slate-500">No emails yet. Upload an .eml file.</p>}

      <ul className="flex flex-col gap-2">
        {scenarios?.map((s) => {
          const selected = s.id === selectedId;
          return (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => onSelect(s.id)}
                aria-current={selected ? "true" : undefined}
                className={`w-full rounded-lg border p-3 text-left transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 ${
                  selected ? "border-indigo-400 bg-indigo-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate font-medium">{s.from_name || s.from_addr}</span>
                  {s.has_attachments && <span className="shrink-0 rounded bg-slate-100 px-1.5 text-xs text-slate-600">PDF</span>}
                </div>
                <div className="truncate font-mono text-xs text-slate-500">{s.from_addr}</div>
                <div className="mt-1 truncate text-sm text-slate-700">{s.subject}</div>
                <div className="mt-1.5 text-xs text-indigo-700">{s.title}</div>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
