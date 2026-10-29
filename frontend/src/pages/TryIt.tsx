import { useCallback, useEffect, useRef, useState } from "react";
import { fetchScenarios, streamCheck } from "../api";
import type { Delivery } from "../compose";
import Composer from "../components/Composer";
import EmailPane from "../components/EmailPane";
import Inbox from "../components/Inbox";
import ResultPane, { initialCheck, type CheckState } from "../components/ResultPane";
import type { CheckEvent, EmailView, ScenarioItem } from "../types";

type Source =
  | { kind: "scenario"; id: string }
  | { kind: "upload"; file: File }
  | { kind: "compose"; eml: string; delivery: Delivery };
type Tab = "inbox" | "compose";
const TABS: { id: Tab; label: string }[] = [
  { id: "inbox", label: "Sample inbox" },
  { id: "compose", label: "Write an email" },
];

export default function TryIt() {
  const [scenarios, setScenarios] = useState<ScenarioItem[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [email, setEmail] = useState<EmailView | null>(null);
  const [check, setCheck] = useState<CheckState>(initialCheck);
  const [tab, setTab] = useState<Tab>("inbox");
  const inFlight = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchScenarios().then(setScenarios).catch(() => setLoadError("Could not load the inbox. Is the server running?"));
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
      : ["/api/check", src.kind === "upload" ? src.file : src.eml];
    streamCheck(url, body, onEvent, controller.signal).catch((err: Error) => {
      if (controller.signal.aborted) return;
      setCheck((c) => ({ ...c, status: "error", error: err.message || "Could not check this email." }));
    });
  }, []);

  function switchTab(t: Tab) {
    inFlight.current?.abort(); // each tab starts with an empty result
    setTab(t);
    setSource(null);
    setEmail(null);
    setCheck(initialCheck);
  }

  const selectedId = source?.kind === "scenario" ? source.id : null;
  const simulated = source?.kind === "compose" && (
    <p className="rounded-lg border border-slate-200 bg-white p-3 text-xs text-slate-600">
      Delivery result is simulated: you chose "{source.delivery === "pass" ? "Passed" : "Failed"} sender checks".
      A real email gets this from the receiving mail server.
    </p>
  );

  return (
    <div className="mx-auto max-w-[1600px] px-4 py-5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Try BEC Guard</h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            You are Jordan, the accounts payable clerk at Riverbend Dental Partners (fictional). Open a sample email or
            write your own, and see what BEC Guard shows next to it in Gmail. The AI analysis is real; companies,
            people and web facts are fictional.
          </p>
        </div>
        <nav aria-label="Try it" className="flex gap-1 rounded-lg bg-slate-100 p-1">
          {TABS.map((t) => (
            <button key={t.id} type="button" onClick={() => switchTab(t.id)} aria-current={tab === t.id ? "page" : undefined}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-blue-600 ${
                tab === t.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
              }`}>
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      <aside aria-label="About this page" className="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-950">
        <h3 className="font-semibold">About this page</h3>
        <ul className="mt-2 flex list-disc flex-col gap-1.5 pl-5">
          <li>
            The real product experience is in the demo video: BEC Guard working inside Gmail, with the card next to the
            email, inbox labels and account-takeover alerts. This page is for testing how the checks work on emails.
          </li>
          <li>
            It uses the same company as the Gmail demo: Riverbend Dental's people, vendors, Acme's bank account on file
            and invoice history. Only the email addresses differ; the demo used our own test Gmail, Yahoo and Outlook
            accounts.
          </li>
          <li>
            If you'd like to see BEC Guard or use it inside Gmail yourself, I can share the login details of the
            Gmail test accounts used in the video. Please let me know.
          </li>
        </ul>
      </aside>

      {tab === "inbox" && (
        <main className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)_26rem]">
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
      )}
      {tab === "compose" && (
        <main className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_26rem]">
          <Composer busy={check.status === "running"} onCheck={(eml, delivery) => run({ kind: "compose", eml, delivery })} />
          <div className="flex flex-col gap-3">
            {simulated}
            <ResultPane check={check} onRetry={() => source && run(source)} />
          </div>
        </main>
      )}
    </div>
  );
}
