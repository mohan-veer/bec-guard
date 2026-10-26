import { useCallback, useEffect, useRef, useState } from "react";
import { fetchHealth, fetchScenarios, streamCheck } from "./api";
import EmailPane from "./components/EmailPane";
import Inbox from "./components/Inbox";
import MailboxView from "./components/MailboxView";
import ModelRouting from "./components/ModelRouting";
import ResultPane, { initialCheck, type CheckState } from "./components/ResultPane";
import type { CheckEvent, EmailView, ScenarioItem } from "./types";

type Source = { kind: "scenario"; id: string } | { kind: "upload"; file: File };
type Tab = "email" | "mailbox";
const TABS: { id: Tab; label: string }[] = [
  { id: "email", label: "Email check" },
  { id: "mailbox", label: "Mailbox check" },
];

export default function App() {
  const [scenarios, setScenarios] = useState<ScenarioItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [mode, setMode] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [email, setEmail] = useState<EmailView | null>(null);
  const [check, setCheck] = useState<CheckState>(initialCheck);
  const [tab, setTab] = useState<Tab>("email");
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchScenarios().then(setScenarios).catch(() => setLoadError("Could not load the inbox. Is the server running?"));
    fetchHealth().then((h) => setMode(h.llm_mode === "real" ? "Live models" : "Mock mode")).catch(() => setMode(null));
  }, []);

  const run = useCallback((src: Source) => {
    inFlight.current?.abort(); // a newer selection replaces the running check
    const controller = new AbortController();
    inFlight.current = controller;
    setSource(src);
    setEmail(null);
    setCheck({ ...initialCheck, status: "running" });
    // On phones the panes stack; jump to the result so the action is visible without scrolling past the inbox.
    if (window.matchMedia("(max-width: 1023px)").matches) {
      document.getElementById("result")?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    const onEvent = (ev: CheckEvent) => {
      if (controller.signal.aborted) return;
      setCheck((c) => {
        switch (ev.type) {
          case "gate": return { ...c, intent: ev.intent };
          case "signals": return { ...c, groupEvents: { ...c.groupEvents, [ev.group]: c.groupEvents[ev.group] + 1 } };
          case "early": return { ...c, early: { decision: ev.decision, reason: ev.reason } };
          case "result": return { ...c, status: "done", card: ev.card };
          case "error": return { ...c, status: "error", error: ev.message };
          default: return c;
        }
      });
      if (ev.type === "email") setEmail(ev.email);
    };

    const [url, body] = src.kind === "scenario"
      ? [`/api/scenarios/${encodeURIComponent(src.id)}/check`, null]
      : ["/api/check", src.file];
    streamCheck(url, body, onEvent, controller.signal).catch((err: Error) => {
      if (controller.signal.aborted) return;
      setCheck((c) => ({ ...c, status: "error", error: err.message || "Could not check this email." }));
    });
  }, []);

  const selectedId = source?.kind === "scenario" ? source.id : null;

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <span aria-hidden className="flex size-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">BG</span>
            <div>
              <h1 className="text-base font-semibold leading-tight">BEC Guard</h1>
              <p className="hidden text-xs text-slate-500 sm:block">Checks payment and data requests before you act on them</p>
            </div>
          </div>
          <nav aria-label="Sections" className="flex gap-1 rounded-lg bg-slate-100 p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                aria-current={tab === t.id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-indigo-600 ${
                  tab === t.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            {mode && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">{mode}</span>}
            <ModelRouting />
          </div>
        </div>
      </header>

      {tab === "mailbox" && <main className="px-4 py-5"><MailboxView /></main>}
      <main hidden={tab !== "email"} className="mx-auto grid max-w-[1600px] gap-5 px-4 py-5 lg:grid-cols-[18rem_minmax(0,1fr)_26rem]">
        <Inbox
          scenarios={scenarios}
          loadError={loadError}
          selectedId={selectedId}
          onSelect={(id) => run({ kind: "scenario", id })}
          onUpload={(file) => run({ kind: "upload", file })}
          onUploadError={(message) => { setSource(null); setEmail(null); setCheck({ ...initialCheck, status: "error", error: message }); }}
        />
        <EmailPane email={email} loading={check.status === "running"} />
        <ResultPane check={check} onRetry={() => source && run(source)} />
      </main>
    </div>
  );
}
