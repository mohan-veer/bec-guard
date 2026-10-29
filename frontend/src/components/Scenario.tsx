import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";

/** The story of one payment scam, in scenes. Presenter-controlled (← → P, or the buttons); autoplays until touched,
 *  so a voice-over never has to match a fixed timeline. All people and companies are fictional. */
const SCENES = [
  { title: "Meet Jordan", text: "Jordan pays the bills at Riverbend Dental. Acme Supply is their biggest vendor, paid every month to the bank account ending 4821." },
  { title: "Ting: an email from Sam at Acme", text: "It comes from Sam's real address, passes every sender check, and replies to the invoice thread Jordan already knows." },
  { title: "But Sam's mailbox was hacked", text: "The attacker writes from inside it: \"We changed banks. Please pay invoice ACM-10437 to our new account today, by wire.\"" },
  { title: "Jordan pays. The money is gone.", text: "$18,400 lands in the attacker's account ending 7731. Getting a wire back after it lands is hard and often fails." },
  { title: "The same email, with BEC Guard", text: "A card opens next to the email: Verify before paying. The new account doesn't match the records; the last 6 invoices went to 4821." },
  { title: "Jordan calls the number on file", text: "BEC Guard shows Acme's phone number from the vendor records, never a number written in the email. Sam: \"We never sent that.\"" },
  { title: "$18,400 saved", text: "One phone call, before paying. That is the whole habit BEC Guard builds, at the moment it matters." },
  { title: "And if Jordan's own mailbox is taken over", text: "A hidden filter, bank details sent from Jordan's account, sent mail deleted: BEC Guard shows a banner and emails the compliance team within about a minute." },
];
const AUTOPLAY_MS = 6500; // arbitrary — long enough to read a caption

function Show({ on, children, from = "translate(0px, 10px)" }: { on: boolean; children: ReactNode; from?: string }) {
  const style: CSSProperties = { opacity: on ? 1 : 0, transform: on ? "none" : from, transition: "opacity .6s, transform .7s" };
  return <g style={style} className="motion-reduce:transition-none" aria-hidden={!on}>{children}</g>;
}

function Stage({ s }: { s: number }) {
  const guard = s >= 4;
  return (
    <svg viewBox="0 0 800 450" role="img" aria-label={SCENES[s].title} className="h-auto w-full">
      <defs>
        <clipPath id="screen"><rect x="210" y="70" width="300" height="210" rx="4" /></clipPath>
      </defs>
      <rect width="800" height="450" fill="#eff6ff" />
      <rect y="400" width="800" height="50" fill="#dbeafe" />

      {/* Without / with BEC Guard */}
      <g>
        <rect x="290" y="16" width="140" height="28" rx="14" fill={guard ? "#2563eb" : "#94a3b8"} style={{ transition: "fill .6s" }} />
        <text x="360" y="35" textAnchor="middle" fontSize="13" fontWeight="600" fill="#fff">{guard ? "With BEC Guard" : "Without BEC Guard"}</text>
      </g>

      {/* Desk, chair, Jordan */}
      <rect x="60" y="300" width="480" height="12" rx="3" fill="#94a3b8" />
      <rect x="80" y="312" width="10" height="88" fill="#94a3b8" /><rect x="510" y="312" width="10" height="88" fill="#94a3b8" />
      <rect x="84" y="232" width="10" height="110" rx="4" fill="#475569" />
      <rect x="84" y="318" width="80" height="10" rx="4" fill="#475569" />
      <rect x="100" y="236" width="52" height="84" rx="20" fill="#0d9488" />
      <path d="M140 262 L200 292" stroke="#0d9488" strokeWidth="14" strokeLinecap="round" />
      <circle cx="128" cy="212" r="24" fill="#f2c9a0" />
      <path d="M104 208 a24 24 0 0 1 48 -4 q-20 -10 -48 4z" fill="#3f2a1d" />
      <text x="128" y="438" textAnchor="middle" fontSize="15" fontWeight="600" fill="#334155">Jordan · Riverbend</text>

      {/* Monitor */}
      <rect x="200" y="60" width="320" height="230" rx="10" fill="#1e293b" />
      <rect x="345" y="290" width="30" height="10" fill="#334155" />
      <g clipPath="url(#screen)">
        <rect x="210" y="70" width="300" height="210" fill="#fff" />
        {/* inbox */}
        <Show on={s < 2}>
          {[100, 132, 164, 196, 228].map((y) => (
            <g key={y}><circle cx="228" cy={y} r="6" fill="#cbd5e1" /><rect x="242" y={y - 5} width="200" height="10" rx="5" fill="#e2e8f0" /></g>
          ))}
        </Show>
        {/* notification */}
        <Show on={s === 1} from="translate(0px, -20px)">
          <g className={s === 1 ? "anim-pop" : ""}>
            <rect x="318" y="80" width="184" height="42" rx="8" fill="#fff" stroke="#3b82f6" strokeWidth="2" />
            <text x="332" y="98" fontSize="12" fontWeight="700" fill="#1e293b">🔔 New email</text>
            <text x="332" y="114" fontSize="11" fill="#475569">Sam Ortiz · Re: Invoice ACM-10437</text>
          </g>
        </Show>
        {/* open email */}
        <Show on={s >= 2}>
          <rect x="210" y="70" width="300" height="34" fill="#f1f5f9" />
          <text x="222" y="91" fontSize="12" fontWeight="700" fill="#1e293b">Sam Ortiz · ar@acmesupply.com</text>
          <text x="222" y="126" fontSize="13" fill="#334155">We changed banks.</text>
          <text x="222" y="150" fontSize="13" fontWeight="700" fill="#b91c1c">New account ending 7731</text>
          <text x="222" y="174" fontSize="13" fill="#334155">Please pay $18,400 today,</text>
          <text x="222" y="194" fontSize="13" fill="#334155">by wire.</text>
          <text x="222" y="226" fontSize="13" fill="#334155">Thanks, Sam</text>
        </Show>
        {/* BEC Guard card */}
        <Show on={guard && s < 7} from="translate(130px, 0px)">
          <rect x="384" y="70" width="126" height="210" fill="#fffbeb" stroke="#f59e0b" strokeWidth="2" />
          <rect x="384" y="70" width="126" height="44" fill="#d97706" />
          <text x="447" y="89" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">Verify before</text>
          <text x="447" y="105" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">paying</text>
          <text x="394" y="134" fontSize="10.5" fill="#92400e">⚠ New account ••7731</text>
          <text x="394" y="154" fontSize="10.5" fill="#92400e">Records: ••4821 ×6</text>
          <text x="394" y="174" fontSize="10.5" fill="#92400e">⚠ ACH → wire</text>
          <text x="394" y="204" fontSize="10.5" fontWeight="700" fill="#1e293b">Call Acme first:</text>
          <text x="394" y="222" fontSize="10.5" fill="#1e293b">(503) 555-0142</text>
          <text x="394" y="238" fontSize="9" fill="#64748b">from vendor records</text>
        </Show>
        {/* takeover banner */}
        <Show on={s === 7} from="translate(0px, -30px)">
          <rect x="210" y="70" width="300" height="40" fill="#b91c1c" />
          <text x="360" y="87" textAnchor="middle" fontSize="11.5" fontWeight="700" fill="#fff">Your mailbox may be in</text>
          <text x="360" y="102" textAnchor="middle" fontSize="11.5" fontWeight="700" fill="#fff">someone else's hands</text>
        </Show>
      </g>

      {/* Acme building + Sam */}
      <rect x="605" y="90" width="160" height="160" fill="#cbd5e1" />
      <rect x="595" y="80" width="180" height="16" fill="#94a3b8" />
      <rect x="625" y="104" width="120" height="24" rx="3" fill="#fff" />
      <text x="685" y="121" textAnchor="middle" fontSize="13" fontWeight="700" fill="#334155">ACME SUPPLY</text>
      {[640, 685, 730].map((x) => <rect key={x} x={x - 12} y="142" width="24" height="24" fill="#e2e8f0" />)}
      <rect x="670" y="200" width="30" height="50" fill="#64748b" />
      <circle cx="575" cy="196" r="16" fill="#c68642" />
      <rect x="559" y="214" width="32" height="40" rx="12" fill="#0e7490" />
      <text x="685" y="272" textAnchor="middle" fontSize="15" fontWeight="600" fill="#334155">Sam · Acme Supply</text>

      {/* attacker inside Sam's mailbox */}
      <Show on={s === 2 || s === 3}>
        <rect x="640" y="36" width="130" height="26" rx="13" fill="#dc2626" />
        <text x="705" y="54" textAnchor="middle" fontSize="12" fontWeight="700" fill="#fff">Mailbox hacked</text>
        <path d="M722 236 q0 -52 28 -52 q28 0 28 52z" fill="#0f172a" />
        <circle cx="750" cy="206" r="13" fill="#1e293b" />
        <circle cx="745" cy="205" r="2" fill="#f87171" /><circle cx="755" cy="205" r="2" fill="#f87171" />
      </Show>

      {/* attacker's bank + money */}
      <Show on={s === 3}>
        <path d="M610 330 L685 300 L760 330z" fill="#7f1d1d" />
        {[625, 655, 685, 715, 745].map((x) => <rect key={x} x={x - 6} y="334" width="12" height="46" fill="#991b1b" />)}
        <rect x="608" y="380" width="154" height="10" fill="#7f1d1d" />
        <text x="685" y="414" textAnchor="middle" fontSize="13" fontWeight="700" fill="#991b1b">Attacker's bank ••7731</text>
        <text x="600" y="296" textAnchor="end" fontSize="20" fontWeight="800" fill="#b91c1c">−$18,400</text>
        {s === 3 && [0, 1, 2].map((i) => (
          <g key={i} className="anim-fly" style={{ animationDelay: `${i * 0.35}s` }}>
            <rect x="340" y="236" width="40" height="22" rx="3" fill="#16a34a" />
            <text x="360" y="252" textAnchor="middle" fontSize="13" fontWeight="800" fill="#dcfce7">$</text>
          </g>
        ))}
      </Show>

      {/* phone call */}
      <Show on={s === 5}>
        <text x="160" y="180" fontSize="28">📞</text>
        <path d="M190 170 Q380 10 560 176" fill="none" stroke="#2563eb" strokeWidth="3" strokeDasharray="8 8" />
        <rect x="540" y="130" width="170" height="38" rx="10" fill="#fff" stroke="#2563eb" strokeWidth="2" />
        <text x="625" y="154" textAnchor="middle" fontSize="13" fontWeight="700" fill="#1e293b">"We never sent that."</text>
      </Show>

      {/* saved */}
      <Show on={s === 6}>
        <circle cx="685" cy="345" r="42" fill="#16a34a" />
        <path d="M665 345 l14 14 l26 -28" fill="none" stroke="#fff" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" />
        <text x="600" y="300" textAnchor="end" fontSize="20" fontWeight="800" fill="#15803d">$18,400 saved</text>
      </Show>

      {/* compliance alert */}
      <Show on={s === 7}>
        <rect x="16" y="16" width="200" height="44" rx="10" fill="#fff" stroke="#b91c1c" strokeWidth="2" />
        <text x="32" y="44" fontSize="13" fontWeight="700" fill="#1e293b">✉ Compliance team alerted</text>
        <g className={s === 7 ? "anim-mail" : ""}><text x="300" y="130" fontSize="26">✉</text></g>
      </Show>
    </svg>
  );
}

export default function Scenario() {
  const [s, setS] = useState(0);
  const [playing, setPlaying] = useState(true);
  const go = useCallback((n: number) => { setPlaying(false); setS(((n % SCENES.length) + SCENES.length) % SCENES.length); }, []);

  useEffect(() => {
    if (!playing) return;
    const t = setTimeout(() => setS((x) => (x + 1) % SCENES.length), AUTOPLAY_MS);
    return () => clearTimeout(t);
  }, [playing, s]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input, textarea, select, [contenteditable]")) return;
      if (e.key === "ArrowRight") go(s + 1);
      else if (e.key === "ArrowLeft") go(s - 1);
      else if (e.key === "p" || e.key === "P") setPlaying((p) => !p);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [s, go]);

  const btn = "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-blue-600";
  return (
    <section aria-label="How a payment scam happens" className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button type="button" onClick={() => go(s + 1)} className="block w-full cursor-pointer" aria-label="Next scene">
        <Stage s={s} />
      </button>
      <div className="flex flex-col gap-3 border-t border-slate-100 p-4 sm:p-5">
        <div aria-live="polite" className="min-h-24">
          <div className="text-xs font-semibold uppercase tracking-wide text-blue-600">Scene {s + 1} of {SCENES.length}</div>
          <h3 className="mt-1 text-xl font-semibold">{SCENES[s].title}</h3>
          <p className="mt-1 text-slate-600">{SCENES[s].text}</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex gap-1.5" role="group" aria-label="Scenes">
            {SCENES.map((sc, i) => (
              <button key={sc.title} type="button" onClick={() => go(i)} aria-label={`Scene ${i + 1}: ${sc.title}`} aria-current={i === s ? "step" : undefined}
                className={`h-2.5 rounded-full transition-all ${i === s ? "w-6 bg-blue-600" : "w-2.5 bg-slate-300 hover:bg-slate-400"}`} />
            ))}
          </div>
          <div className="flex gap-2">
            <button type="button" className={btn} onClick={() => go(s - 1)}>← Back</button>
            <button type="button" className={btn} onClick={() => setPlaying((p) => !p)}>{playing ? "Pause" : "Play"}</button>
            <button type="button" className={btn} onClick={() => go(s + 1)}>Next →</button>
          </div>
        </div>
      </div>
    </section>
  );
}
