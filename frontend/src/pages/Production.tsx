import { useState, type ReactNode } from "react";

type IconName = "mail" | "plug" | "bolt" | "eye" | "server" | "chip" | "book" | "lock" | "bell";

const PATHS: Record<IconName, ReactNode> = {
  mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>,
  plug: <><path d="M9 3v5M15 3v5" /><path d="M6 8h12v3a6 6 0 0 1-12 0z" /><path d="M12 17v4" /></>,
  bolt: <path d="M13 2 4 14h7l-1 8 9-12h-7z" />,
  eye: <><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z" /><circle cx="12" cy="12" r="3" /></>,
  server: <><rect x="3" y="4" width="18" height="7" rx="1.5" /><rect x="3" y="13" width="18" height="7" rx="1.5" /><path d="M7 7.5h.01M7 16.5h.01" /></>,
  chip: <><rect x="6" y="6" width="12" height="12" rx="2" /><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" /></>,
  book: <><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z" /><path d="M4 19V5" /></>,
  lock: <><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>,
  bell: <><path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z" /><path d="M10 21h4" /></>,
};

function Icon({ name, className = "size-5" }: { name: IconName; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden>
      {PATHS[name]}
    </svg>
  );
}

type Row = { icon: IconName; layer: string; demo: string; prod: string; why: string; tag?: "same" | "added" };

const ROWS: Row[] = [
  { icon: "mail", layer: "Mailboxes", demo: "One Gmail test mailbox",
    prod: "Every mailbox in the company: Google Workspace and Microsoft 365 (Outlook)",
    why: "Most small and mid-size companies run on one of the two. The checks don't depend on the provider." },
  { icon: "plug", layer: "Install", demo: "Apps Script test deployment, installed by hand",
    prod: "Google Workspace Marketplace add-on and Outlook add-in (Microsoft AppSource); an admin installs it once for everyone",
    why: "No code in the customer's account, one click for the whole company. Needs Google's and Microsoft's app review, which takes weeks." },
  { icon: "bolt", layer: "New mail", demo: "Checked every minute (Apps Script timer)",
    prod: "Push events: Gmail Pub/Sub and Microsoft Graph change notifications",
    why: "Warnings in seconds instead of up to a minute, and no daily timer quota." },
  { icon: "eye", layer: "Takeover signals", tag: "added",
    demo: "From inside the mailbox: new filters and forwarding, sent and deleted mail",
    prod: "Plus the admin audit logs: sign-ins from new places, rule changes, read on the server",
    why: "An add-on can't see sign-ins, and an intruder could remove it. Google Workspace and Microsoft 365 audit logs are read by the server with the admin's approval, so they keep working even if the add-on is removed." },
  { icon: "server", layer: "BEC Guard API", demo: "One FastAPI server, state held in memory",
    prod: "Nebius Serverless Endpoints for the API, Serverless Jobs for background scans and history import",
    why: "Scales with mail volume per company; long scans run off the request path." },
  { icon: "chip", layer: "AI", tag: "same", demo: "Nemotron Nano, Super, Super VL and Ultra on Nebius Token Factory",
    prod: "Same models, same routing",
    why: "Nano screens every email cheaply; Super, Super VL and Ultra run only when an email asks for money or data." },
  { icon: "book", layer: "Company records", demo: "Vendor records and staff directory in JSON files",
    prod: "Read-only sync from QuickBooks, Xero or NetSuite",
    why: "Bank details always come from the accounting system, never from email, so a poisoned thread can't teach BEC Guard the wrong account." },
  { icon: "lock", layer: "Payment gate", tag: "added", demo: "Warning in the mailbox only",
    prod: "Hold in the bill-pay step: a vendor's changed bank account can't be paid until someone has called back",
    why: "The last line of defence: even an email BEC Guard missed can't send money to a new account unchecked." },
  { icon: "bell", layer: "Alerts and history", demo: "Sidebar banner and an email to the compliance contact in a server file",
    prod: "Database with audit history, admin console with roles, alerts to email, Slack or Teams",
    why: "Survives restarts and shows who acknowledged what. The mailbox owner still can't change who gets alerted." },
];

function Comparison() {
  const [open, setOpen] = useState(3); // start on the biggest change: takeover signals
  return (
    <ol className="flex flex-col gap-3">
      {ROWS.map((r, i) => {
        const on = open === i;
        return (
          <li key={r.layer}>
            <button type="button" onClick={() => setOpen(on ? -1 : i)} aria-expanded={on}
              className={`grid w-full grid-cols-1 gap-3 rounded-2xl border p-3 text-left transition md:grid-cols-[11rem_minmax(0,1fr)_2rem_minmax(0,1.2fr)] md:items-center ${
                on ? "border-blue-300 bg-white shadow-md shadow-blue-100" : "border-slate-200 bg-white/70 hover:border-blue-200"
              }`}>
              <div className="flex items-center gap-2.5">
                <span className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${on ? "bg-blue-600 text-white" : "bg-blue-50 text-blue-700"}`}>
                  <Icon name={r.icon} />
                </span>
                <span className="font-semibold">{r.layer}</span>
              </div>
              <div className="rounded-xl border border-sky-200 bg-sky-50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-wider text-sky-700">Hackathon demo</div>
                <p className="mt-0.5 text-sm text-slate-700">{r.demo}</p>
              </div>
              <span aria-hidden className={`hidden justify-self-center text-xl md:block ${on ? "text-blue-600" : "text-slate-300"}`}>→</span>
              <div className="rounded-xl bg-gradient-to-br from-blue-700 to-blue-900 p-3 text-white">
                <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-blue-200">
                  Production
                  {r.tag === "added" && <span className="rounded bg-sky-400 px-1.5 text-blue-950">new idea</span>}
                  {r.tag === "same" && <span className="rounded bg-white/20 px-1.5 text-white">unchanged</span>}
                </div>
                <p className="mt-0.5 text-sm">{r.prod}</p>
              </div>
              {on && (
                <p className="text-sm text-slate-600 md:col-span-4 md:pl-[11.75rem]">
                  <span className="font-semibold text-blue-800">Why: </span>{r.why}
                </p>
              )}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** Production architecture. Dashed lines flow in the direction data moves (CSS animation, off with reduced motion). */
function Architecture() {
  const box = (x: number, y: number, w: number, h: number, title: string, sub: string, dark = false) => (
    <g>
      <rect x={x} y={y} width={w} height={h} rx="12" fill={dark ? "#1e3a8a" : "#fff"} stroke={dark ? "#1e3a8a" : "#93c5fd"} strokeWidth="1.5" />
      <text x={x + w / 2} y={y + h / 2 - 4} textAnchor="middle" fontSize="14" fontWeight="700" fill={dark ? "#fff" : "#0f172a"}>{title}</text>
      <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" fontSize="11" fill={dark ? "#bfdbfe" : "#475569"}>{sub}</text>
    </g>
  );
  const flow = (d: string, label?: [number, number, string]) => (
    <g>
      <path d={d} fill="none" stroke="#2563eb" strokeWidth="2" strokeDasharray="6 6" className="anim-flow" markerEnd="url(#arrow)" />
      {label && <text x={label[0]} y={label[1]} textAnchor="middle" fontSize="10.5" fill="#1d4ed8">{label[2]}</text>}
    </g>
  );
  return (
    <div className="overflow-x-auto rounded-2xl border border-blue-100 bg-gradient-to-b from-blue-50 to-white p-3">
      <svg viewBox="0 0 900 400" role="img" aria-label="Production architecture" className="h-auto w-full min-w-[44rem]">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10z" fill="#2563eb" />
          </marker>
        </defs>
        <text x="20" y="28" fontSize="12" fontWeight="700" fill="#64748b" letterSpacing="1">CUSTOMER</text>
        <text x="345" y="28" fontSize="12" fontWeight="700" fill="#64748b" letterSpacing="1">NEBIUS</text>
        <text x="690" y="28" fontSize="12" fontWeight="700" fill="#64748b" letterSpacing="1">CUSTOMER SYSTEMS</text>
        <rect x="330" y="40" width="300" height="340" rx="16" fill="#dbeafe" opacity="0.6" />

        {box(20, 50, 240, 64, "Gmail · Outlook", "every mailbox in the company")}
        {box(20, 168, 240, 64, "BEC Guard add-on", "card next to the email, banner")}
        {box(20, 286, 240, 64, "Admin audit logs", "sign-ins, rule changes")}

        {box(350, 60, 260, 70, "BEC Guard API", "Serverless Endpoints", true)}
        {box(350, 168, 260, 64, "Nemotron on Token Factory", "Nano · Super · Super VL · Ultra")}
        {box(350, 286, 260, 64, "Serverless Jobs + database", "mailbox scans, audit history")}

        {box(660, 50, 220, 64, "Accounting system", "QuickBooks · Xero · NetSuite")}
        {box(660, 168, 220, 64, "Bill pay", "payment gate on bank changes")}
        {box(660, 286, 220, 64, "Compliance team", "email · Slack · Teams")}

        {flow("M260 82 L346 90", [300, 76, "push events"])}
        {flow("M346 110 L262 190", [290, 160, "result card"])}
        {flow("M260 318 L346 318", [300, 310, "audit events"])}
        {flow("M480 130 L480 164")}
        {flow("M480 286 L480 236")}
        {flow("M656 82 L614 92", [636, 72, "records"])}
        {flow("M612 115 L656 190", [650, 150, "hold"])}
        {flow("M612 125 Q640 240 656 304", [622, 270, "alerts"])}
      </svg>
    </div>
  );
}

export default function Production() {
  return (
    <main className="flex flex-col">
      <section className="bg-gradient-to-br from-blue-900 via-blue-800 to-sky-700 text-white">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <p className="text-sm font-semibold uppercase tracking-wider text-sky-200">From demo to product</p>
          <h2 className="mt-2 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">Shown on Gmail. Designed for every mailbox.</h2>
          <p className="mt-4 max-w-3xl text-blue-100">
            With a hackathon's limited resources, the demo runs on Gmail with an Apps Script add-on, a records file and one
            server. With the budget for a real product (paid app reviews, accounting integrations, production hosting),
            this is what we would build. The checks, the rules and the Nemotron models stay the same.
          </p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl bg-white/10 p-4 ring-1 ring-white/20">
              <div className="text-xs font-bold uppercase tracking-wider text-sky-200">Hackathon demo · running today</div>
              <p className="mt-1 text-sm">Gmail add-on, every-minute checks, takeover alerts to compliance, Nemotron on Nebius Token Factory.</p>
            </div>
            <div className="rounded-xl bg-white p-4 text-slate-900 shadow-lg">
              <div className="text-xs font-bold uppercase tracking-wider text-blue-700">Production · the plan</div>
              <p className="mt-1 text-sm">Gmail and Outlook for the whole company, push events, audit logs, accounting sync and a payment gate.</p>
            </div>
          </div>
        </div>
      </section>

      <div className="mx-auto flex w-full max-w-6xl flex-col gap-10 px-4 py-10">
        <section aria-labelledby="layers">
          <h3 id="layers" className="text-xl font-semibold">What changes, layer by layer</h3>
          <p className="mt-1 text-sm text-slate-600">Click a row to see why it changes.</p>
          <div className="mt-4"><Comparison /></div>
        </section>

        <section aria-labelledby="arch">
          <h3 id="arch" className="text-xl font-semibold">Production architecture</h3>
          <p className="mt-1 text-sm text-slate-600">Mail and audit events flow in; records come from the accounting system; warnings go to the person paying, the payment step and compliance.</p>
          <div className="mt-4"><Architecture /></div>
        </section>

        <section aria-labelledby="ship" className="grid gap-4 md:grid-cols-2">
          <h3 id="ship" className="text-xl font-semibold md:col-span-2">Two ways to ship it</h3>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md">
            <h4 className="font-semibold">Marketplace add-on</h4>
            <p className="mt-1 text-sm text-slate-600">
              Small and mid-size companies install BEC Guard from the Google Workspace Marketplace or Microsoft AppSource
              and connect their accounting system.
            </p>
          </div>
          <div className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:shadow-md">
            <h4 className="font-semibold">Custom integration</h4>
            <p className="mt-1 text-sm text-slate-600">
              For larger customers or email security vendors: the same API behind their own Gmail or Outlook integration,
              with their vendor master data and their alert channels.
            </p>
          </div>
        </section>

        <p className="rounded-2xl border border-blue-100 bg-blue-50 p-5 text-sm text-blue-950">
          <span className="font-semibold">What never changes: </span>a rule decides, never a model; phone numbers to call
          come only from the company's records or the vendor's official website; BEC Guard only adds labels and never
          moves, deletes or forwards mail.
        </p>
      </div>
    </main>
  );
}
