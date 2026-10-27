import type { Card, CardSection, Decision, Group, Signal } from "../types";

export interface CheckState {
  status: "idle" | "running" | "done" | "error";
  intent: string | null;
  groupEvents: Record<Group, number>;
  early: { decision: Decision; reason: string } | null;
  card: Card | null;
  error: string | null;
}

export const initialCheck: CheckState = {
  status: "idle", intent: null, groupEvents: { gate: 0, entity: 0, org: 0, content: 0 }, early: null, card: null, error: null,
};

// Number of "signals" events each group sends (org = fast lookalike + slow RDAP/web agent).
const EXPECTED: Record<Exclude<Group, "gate">, number> = { entity: 1, org: 2, content: 1 };

const STYLES: Record<Decision | "none", { box: string; badge: string; icon: string }> = {
  VERIFY_BEFORE_PAYING: { box: "border-amber-300 bg-amber-50", badge: "bg-amber-600 text-white", icon: "!" },
  LOOKS_UNUSUAL: { box: "border-yellow-300 bg-yellow-50", badge: "bg-yellow-500 text-yellow-950", icon: "?" },
  NO_ISSUES_FOUND: { box: "border-emerald-300 bg-emerald-50", badge: "bg-emerald-600 text-white", icon: "✓" },
  none: { box: "border-slate-200 bg-slate-50", badge: "bg-slate-500 text-white", icon: "–" },
};

const GROUP_LABELS: Record<Group, string> = { gate: "Request", entity: "Sender", org: "Domain & web", content: "Content" };

function Spinner() {
  return <span aria-hidden className="inline-block size-3.5 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-600" />;
}

function Progress({ check }: { check: CheckState }) {
  const steps: { label: string; done: boolean }[] = [
    { label: "Request type · Nemotron Nano", done: check.intent !== null },
    { label: "Sender and email headers · rules", done: check.groupEvents.entity >= EXPECTED.entity },
    { label: "Domain, website, phone · RDAP + Nemotron Super agent with Tavily", done: check.groupEvents.org >= EXPECTED.org },
    { label: "Payment details, language, style · rules + Nemotron Super / VL", done: check.groupEvents.content >= EXPECTED.content },
  ];
  const allDone = steps.every((s) => s.done);
  return (
    <ol className="flex flex-col gap-2 text-sm">
      {steps.map((s) => (
        <li key={s.label} className="flex items-center gap-2">
          {s.done ? <span aria-hidden className="text-emerald-600">✓</span> : <Spinner />}
          <span className={s.done ? "text-slate-700" : "text-slate-500"}>{s.label}</span>
          <span className="sr-only">{s.done ? "done" : "in progress"}</span>
        </li>
      ))}
      {allDone && (
        <li className="flex items-center gap-2">
          <Spinner /> <span className="text-slate-500">Writing summary · Nemotron Ultra</span>
        </li>
      )}
    </ol>
  );
}

const ITEM_STYLE = {
  warn: { icon: "⚠", color: "text-amber-600" },
  note: { icon: "ℹ", color: "text-slate-400" },
  ok: { icon: "✓", color: "text-emerald-600" },
} as const;

function SectionList({ section }: { section: CardSection }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-700">{section.title}</h3>
      <ul className="mt-1.5 flex flex-col gap-1 text-sm">
        {section.items.map((item, i) => (
          <li key={`${item.code}-${i}`} className="flex gap-2">
            <span aria-hidden className={ITEM_STYLE[item.tone].color}>{ITEM_STYLE[item.tone].icon}</span>
            <span className={item.tone === "ok" ? "text-slate-600" : ""}>
              {item.text}
              {item.sources?.filter((s) => /^https?:\/\//.test(s.url)).map((s) => (
                <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer"
                   className="ml-2 inline-block rounded bg-slate-100 px-1.5 py-0.5 text-xs text-indigo-700 hover:underline">
                  {new URL(s.url).hostname.replace(/^www\./, "")}
                </a>
              ))}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HowChecked({ checks, rule }: { checks: Signal[]; rule: string | null }) {
  const icon = { fine: "✓", unusual: "!", info: "i" } as const;
  const color = { fine: "text-emerald-600", unusual: "text-amber-600", info: "text-slate-400" } as const;
  return (
    <details className="group rounded-lg border border-slate-200 bg-white">
      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50">
        How this was checked ({checks.length} checks)
      </summary>
      <div className="border-t border-slate-100 px-4 py-3">
        {rule && (
          <p className="mb-3 text-xs text-slate-500">
            Decided by scorer rule <code className="rounded bg-slate-100 px-1">{rule}</code>. No AI model makes the decision;
            models only produce findings.
          </p>
        )}
        <ul className="flex flex-col gap-2.5">
          {checks.map((c, i) => (
            <li key={`${c.code}-${i}`} className="grid grid-cols-[1rem_1fr] gap-x-2 text-sm">
              <span aria-label={c.verdict} className={`font-bold ${color[c.verdict]}`}>{icon[c.verdict]}</span>
              <div className="min-w-0">
                <div className="break-words">{c.message}</div>
                <div className="mt-0.5 flex flex-wrap gap-1.5 text-xs">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">{GROUP_LABELS[c.group]}</span>
                  <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-700">{c.source}</span>
                  {c.verdict === "unusual" && c.weight !== "none" && (
                    <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-800">{c.weight}</span>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

function ResultCard({ card }: { card: Card }) {
  const style = STYLES[card.decision ?? "none"];
  return (
    <div className="flex flex-col gap-4">
      <div className={`rounded-xl border-2 p-5 ${style.box}`}>
        <div className="flex items-center gap-2">
          <span aria-hidden className={`flex size-6 items-center justify-center rounded-full text-sm font-bold ${style.badge}`}>{style.icon}</span>
          <h2 className="text-base font-semibold">{card.headline}</h2>
        </div>
        {card.intro && <p className="mt-2 text-sm text-slate-700">{card.intro}</p>}
        {card.action && <p className="mt-3 text-[15px] leading-relaxed font-medium">{card.action}</p>}
      </div>
      {card.sections.map((s) => <SectionList key={s.title} section={s} />)}
      <HowChecked checks={card.checks} rule={card.rule} />
    </div>
  );
}

export default function ResultPane({ check, onRetry }: { check: CheckState; onRetry: () => void }) {
  return (
    <section id="result" aria-label="Result" aria-live="polite" aria-busy={check.status === "running"} className="flex scroll-mt-20 flex-col gap-4">
      {check.status === "idle" && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-sm text-slate-500">
          The result appears here: what to do first, then what looks fine and what looks unusual.
        </div>
      )}
      {check.status === "error" && (
        <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
          <p>{check.error}</p>
          <button type="button" onClick={onRetry} className="mt-3 rounded-md bg-white px-3 py-1.5 font-medium text-red-800 shadow-sm ring-1 ring-red-200 hover:bg-red-100">
            Try again
          </button>
        </div>
      )}
      {check.status === "running" && (
        <>
          {check.early && (
            <div role="alert" className={`rounded-xl border-2 p-5 ${STYLES.VERIFY_BEFORE_PAYING.box}`}>
              <h2 className="font-semibold">Verify before paying</h2>
              <p className="mt-2 text-sm">{check.early.reason}</p>
              <p className="mt-2 text-xs text-slate-600">Still finishing the other checks and looking up a phone number to call…</p>
            </div>
          )}
          <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="mb-3 text-sm font-semibold text-slate-700">Checking this email…</h2>
            <Progress check={check} />
          </div>
        </>
      )}
      {check.status === "done" && check.card && <ResultCard card={check.card} />}
    </section>
  );
}
