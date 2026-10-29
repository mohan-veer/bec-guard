import { useRef } from "react";

// Brief §5: which model or tool does each step. The decision itself is made by rules, never by a model.
const ROWS = [
  ["Is this a money or data request?", "Nemotron Nano", "Cheap and fast; runs on every email"],
  ["Read bank details from PDF or image attachments", "Nemotron Super VL", "Wire instructions often hide in PDFs"],
  ["Urgency, secrecy, request type, writing style", "Nemotron Super", "Needs judgment"],
  ["Official website and phone lookup", "Nemotron Super agent + Tavily", "Independent verification; the agent chooses its searches"],
  ["Plain-English explanation (only when something needs checking)", "Nemotron Ultra (fallback: Super)", "Best wording, used rarely"],
  ["Decision", "Rules (scorer)", "Deterministic; no model decides"],
];

export default function ModelRouting() {
  const dialog = useRef<HTMLDialogElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => dialog.current?.showModal()}
        className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-600"
      >
        Models
      </button>
      <dialog
        ref={dialog}
        aria-labelledby="routing-title"
        className="m-auto w-[min(44rem,calc(100vw-2rem))] rounded-xl p-0 shadow-xl backdrop:bg-slate-900/40"
        onClick={(e) => e.target === dialog.current && dialog.current?.close()}
      >
        <div className="p-6">
          <div className="flex items-start justify-between gap-4">
            <h2 id="routing-title" className="text-lg font-semibold">Which model does what</h2>
            <button type="button" onClick={() => dialog.current?.close()} className="rounded-md px-2 py-1 text-slate-500 hover:bg-slate-100" aria-label="Close">
              ✕
            </button>
          </div>
          <p className="mt-1 text-sm text-slate-600">NVIDIA Nemotron models run on Nebius Token Factory. Models produce findings; a rules-based scorer decides.</p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="py-2 pr-3">Step</th><th className="py-2 pr-3">Model / tool</th><th className="py-2">Why</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {ROWS.map(([step, model, why]) => (
                  <tr key={step}>
                    <td className="py-2 pr-3">{step}</td>
                    <td className="py-2 pr-3 font-medium text-blue-700">{model}</td>
                    <td className="py-2 text-slate-600">{why}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </dialog>
    </>
  );
}
