import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

/** The story of one BEC payment scam, 45 s, click to play. It waits on the first frame until started.
 *  The intro and captions are HTML inside the SVG (foreignObject), so everything scales with the player.
 *  All people and companies are fictional. */
const END = 45;
const CAPTIONS: [number, number, string][] = [
  [14, 21, "Every month, Acme Supply sends an invoice, and Jordan pays it: same contact, same bank account."],
  [21, 28, "One day, Sam writes: “We changed banks. Please pay today.” It looks routine, so Jordan pays."],
  [28, 37, "But it wasn’t Sam. The email came from one of three places."],
  [37, 42, "The money lands in the attacker’s account. Before anyone notices, it’s gone."],
];
const LOSS = 3_046_598_558;
const PAYMENTS = [["Jun", "$12,600", 15], ["Jul", "$21,300", 15.8], ["Aug", "$16,450", 16.6], ["Sep", "$19,800", 17.4]] as const;
const TICKS = [["Same name", 24], ["Same invoice", 24.7], ["Same amount", 25.4]] as const;
const ROUTES = [
  { x: 150, title: "Lookalike domain", addr: "ar@acmesuppIy.com", note: "a capital I instead of an l", at: 29.5 },
  { x: 610, title: "Free email account", addr: "sam.ortiz.acme@gmail.com", note: "the right name, the wrong address", at: 31.5 },
  { x: 1070, title: "Hacked real mailbox", addr: "ar@acmesupply.com", note: "Sam's real account, attacker inside", at: 33.5 },
];

function Fade({ on, children, from = "translate(0px, 24px)" }: { on: boolean; children: ReactNode; from?: string }) {
  const style: CSSProperties = { opacity: on ? 1 : 0, transform: on ? "none" : from, transition: "opacity .8s ease, transform .9s ease" };
  return <g style={style}>{children}</g>;
}

function Stage({ t }: { t: number }) {
  const between = (a: number, b: number) => t >= a && t < b;
  const count = Math.round(LOSS * Math.min(1, Math.max(0, (t - 8.4) / 3.6)) ** 0.5);
  const caption = CAPTIONS.find(([a, b]) => between(a, b))?.[2];
  const paid = t >= 26.6;
  return (
    <svg viewBox="0 0 1600 900" className="block h-auto w-full" role="img" aria-label="How a payment scam happens">
      <defs>
        <clipPath id="sp-screen"><rect x="200" y="250" width="440" height="300" rx="6" /></clipPath>
        <marker id="sp-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#dc2626" /></marker>
      </defs>
      <rect width="1600" height="900" fill="#eff6ff" />
      <rect y="780" width="1600" height="120" fill="#dbeafe" />

      {/* the number */}
      <Fade on={between(8, 14)} from="scale(0.96)">
        <text x="800" y="300" textAnchor="middle" fontSize="34" fontWeight="600" fill="#1e3a8a">Business email compromise, 2025</text>
        <text x="800" y="450" textAnchor="middle" fontSize="128" fontWeight="800" fill="#0f172a" style={{ fontVariantNumeric: "tabular-nums" }}>
          ${count.toLocaleString("en-US")}
        </text>
        <text x="800" y="530" textAnchor="middle" fontSize="36" fill="#334155">lost by victims, second only to investment fraud</text>
        <text x="800" y="600" textAnchor="middle" fontSize="24" fill="#64748b">Source: FBI Internet Crime Report 2025</text>
      </Fade>

      {/* the world: Jordan, the screen, Acme and Sam */}
      <g style={{ opacity: between(14, 42) ? (between(28, 37) ? 0.18 : 1) : 0, transition: "opacity .8s ease" }}>
        <rect x="80" y="600" width="660" height="18" rx="4" fill="#94a3b8" />
        <rect x="110" y="618" width="14" height="162" fill="#94a3b8" /><rect x="696" y="618" width="14" height="162" fill="#94a3b8" />
        <rect x="64" y="470" width="14" height="170" rx="6" fill="#475569" />
        <rect x="64" y="586" width="120" height="14" rx="6" fill="#475569" />
        <rect x="86" y="474" width="78" height="124" rx="30" fill="#0d9488" />
        <path d="M146 514 L240 558" stroke="#0d9488" strokeWidth="22" strokeLinecap="round" />
        <circle cx="124" cy="436" r="36" fill="#f2c9a0" />
        <path d="M88 430 a36 36 0 0 1 72 -6 q-30 -16 -72 6z" fill="#3f2a1d" />
        <text x="410" y="700" textAnchor="middle" fontSize="30" fontWeight="700" fill="#1e293b">Jordan · Riverbend Dental</text>
        <rect x="186" y="236" width="468" height="328" rx="16" fill="#1e293b" />
        <rect x="400" y="564" width="40" height="36" fill="#334155" />
        <g clipPath="url(#sp-screen)">
          <rect x="200" y="250" width="440" height="300" fill="#fff" />
          <Fade on={t < 23}>
            {[290, 340, 390, 440, 490].map((y) => (
              <g key={y}><circle cx="232" cy={y} r="10" fill="#cbd5e1" /><rect x="256" y={y - 8} width="300" height="16" rx="8" fill="#e2e8f0" /></g>
            ))}
          </Fade>
          <Fade on={t >= 23}>
            <rect x="200" y="250" width="440" height="50" fill="#f1f5f9" />
            <text x="220" y="283" fontSize="20" fontWeight="700" fill="#1e293b">Sam Ortiz · Re: Invoice ACM-10437</text>
            <text x="220" y="336" fontSize="22" fill="#334155">We changed banks.</text>
            <text x="220" y="372" fontSize="22" fontWeight="700" fill="#b91c1c">New account ending 7731</text>
            <text x="220" y="408" fontSize="22" fill="#334155">Please pay $18,400 today, by wire.</text>
            <rect x="220" y="450" width="200" height="56" rx="12" fill={paid ? "#15803d" : "#2563eb"} style={{ transition: "fill .3s" }} />
            <text x="320" y="486" textAnchor="middle" fontSize="22" fontWeight="700" fill="#fff">{paid ? "Paid ✓" : "Pay $18,400"}</text>
          </Fade>
        </g>
        <g style={{ opacity: t >= 37 ? 0 : 1, transition: "opacity .8s ease" }}>
          <rect x="1180" y="250" width="300" height="300" fill="#cbd5e1" />
          <rect x="1160" y="230" width="340" height="28" fill="#94a3b8" />
          <rect x="1220" y="276" width="220" height="44" rx="6" fill="#fff" />
          <text x="1330" y="307" textAnchor="middle" fontSize="24" fontWeight="800" fill="#334155">ACME SUPPLY</text>
          {[1240, 1310, 1380].map((x) => <rect key={x} x={x} y="350" width="44" height="44" fill="#e2e8f0" />)}
          <rect x="1305" y="460" width="50" height="90" fill="#64748b" />
          <circle cx="1110" cy="400" r="26" fill="#c68642" />
          <rect x="1084" y="430" width="52" height="70" rx="20" fill="#0e7490" />
          <rect x="1088" y="496" width="18" height="56" rx="8" fill="#334155" /><rect x="1114" y="496" width="18" height="56" rx="8" fill="#334155" />
          <text x="1330" y="600" textAnchor="middle" fontSize="28" fontWeight="700" fill="#1e293b">Sam · Acme Supply</text>
          <text x="1330" y="636" textAnchor="middle" fontSize="22" fill="#475569">paid to the account ending 4821</text>
        </g>

        {/* the routine */}
        <Fade on={between(14.5, 21)}><text x="890" y="282" textAnchor="middle" fontSize="24" fontWeight="700" fill="#1e3a8a">Paid to Acme every month</text></Fade>
        {PAYMENTS.map(([month, amount, at], i) => (
          <Fade key={month} on={between(at, 21)} from="translate(0px, 16px)">
            <rect x="720" y={302 + i * 62} width="340" height="50" rx="12" fill="#fff" stroke="#93c5fd" strokeWidth="2" />
            <text x="740" y={335 + i * 62} fontSize="22" fill="#334155">{month} · {amount} → ••4821</text>
            <text x="1036" y={336 + i * 62} textAnchor="end" fontSize="24" fill="#15803d">✓</text>
          </Fade>
        ))}

        {/* why Jordan believes it */}
        {TICKS.map(([label, at], i) => (
          <Fade key={label} on={between(at, 28)} from="translate(-16px, 0px)">
            <rect x="720" y={320 + i * 72} width="300" height="56" rx="28" fill="#dcfce7" stroke="#16a34a" strokeWidth="2" />
            <text x="870" y={357 + i * 72} textAnchor="middle" fontSize="26" fontWeight="700" fill="#166534">✓ {label}</text>
          </Fade>
        ))}
      </g>

      {/* Sam's email flies to Jordan's screen */}
      <g style={{ opacity: between(21.3, 23.3) ? 1 : 0, transform: t >= 21.6 ? "translate(-690px, -70px) scale(0.6)" : "none",
        transformOrigin: "1110px 470px", transition: "opacity .5s ease, transform 1.6s cubic-bezier(.5,0,.3,1)" }}>
        <rect x="1010" y="410" width="200" height="120" rx="14" fill="#fff" stroke="#2563eb" strokeWidth="4" />
        <path d="M1010 422 L1110 480 L1210 422" fill="none" stroke="#2563eb" strokeWidth="4" />
      </g>

      {/* the reveal: it wasn't Sam */}
      <Fade on={between(28, 37)}>
        <path d="M742 230 q0 -96 58 -96 q58 0 58 96z" fill="#0f172a" />
        <circle cx="800" cy="112" r="34" fill="#1e293b" />
        <path d="M760 120 q40 -78 80 0 q-40 -30 -80 0z" fill="#0f172a" />
        <circle cx="788" cy="116" r="4" fill="#f87171" /><circle cx="812" cy="116" r="4" fill="#f87171" />
        <text x="800" y="262" textAnchor="middle" fontSize="26" fontWeight="700" fill="#991b1b">The attacker</text>
        {ROUTES.map((r) => (
          <Fade key={r.title} on={t >= r.at} from="translate(0px, 40px)">
            <path d={`M800 280 L${r.x + 190} 410`} stroke="#dc2626" strokeWidth="4" fill="none" markerEnd="url(#sp-arrow)" />
            <rect x={r.x} y="420" width="380" height="170" rx="20" fill="#fff" stroke="#dc2626" strokeWidth="3" />
            <text x={r.x + 190} y="470" textAnchor="middle" fontSize="30" fontWeight="800" fill="#0f172a">{r.title}</text>
            <text x={r.x + 190} y="518" textAnchor="middle" fontSize="24" fontFamily="ui-monospace, Menlo, monospace" fill="#b91c1c">{r.addr}</text>
            <text x={r.x + 190} y="560" textAnchor="middle" fontSize="21" fill="#475569">{r.note}</text>
          </Fade>
        ))}
      </Fade>

      {/* the money goes */}
      <Fade on={between(37.3, 42)} from="translate(40px, 0px)">
        <path d="M1180 380 L1330 320 L1480 380z" fill="#7f1d1d" />
        {[1205, 1255, 1305, 1355, 1405, 1455].map((x) => <rect key={x} x={x - 9} y="386" width="18" height="90" fill="#991b1b" />)}
        <rect x="1176" y="476" width="308" height="16" fill="#7f1d1d" />
        <text x="1330" y="536" textAnchor="middle" fontSize="28" fontWeight="800" fill="#991b1b">Attacker's bank ••7731</text>
      </Fade>
      {between(38, 42) && [0, 1, 2, 3].map((i) => (
        <g key={i} className="anim-billfly" style={{ animationDelay: `${i * 0.3}s` }}>
          <rect x="300" y="470" width="80" height="44" rx="6" fill="#16a34a" />
          <text x="340" y="502" textAnchor="middle" fontSize="26" fontWeight="800" fill="#dcfce7">$</text>
        </g>
      ))}
      <Fade on={between(39.5, 42)} from="scale(0.9)">
        <text x="1330" y="275" textAnchor="middle" fontSize="64" fontWeight="800" fill="#b91c1c">−$18,400</text>
      </Fade>

      {/* the question */}
      <Fade on={t >= 42} from="scale(0.97)">
        <rect width="1600" height="900" fill="#0b1e4a" />
        <text x="800" y="340" textAnchor="middle" fontSize="70" fontWeight="800" fill="#fff">One email. The money is gone.</text>
        <text x="800" y="440" textAnchor="middle" fontSize="44" fill="#bfdbfe">How do you stop it before you pay?</text>
        <text x="800" y="540" textAnchor="middle" fontSize="34" fill="#93c5fd">BEC Guard checks the request first.</text>
      </Fade>

      {/* the intro (HTML, scales with the player) */}
      <foreignObject x="0" y="0" width="1600" height="900" style={{ opacity: t < 8 ? 1 : 0, transition: "opacity .8s ease", pointerEvents: "none" }}>
        <div style={{ width: 1600, height: 900, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          background: "#eff6ff", padding: "0 130px", boxSizing: "border-box", textAlign: "center", fontFamily: "inherit" }}>
          <div style={{ fontSize: 76, fontWeight: 800, color: "#1e3a8a", marginBottom: 40 }}>Business email compromise</div>
          <p style={{ fontSize: 38, lineHeight: 1.45, color: "#334155", margin: "0 0 22px" }}>
            A criminal pretends to be <mark style={{ background: "#fef08a", padding: "0 6px", borderRadius: 6 }}>someone you already trust</mark>: a vendor, your CEO, a colleague.
          </p>
          <p style={{ fontSize: 38, lineHeight: 1.45, color: "#334155", margin: 0 }}>
            They email a normal-looking request to <mark style={{ background: "#fef08a", padding: "0 6px", borderRadius: 6 }}>send money or sensitive data</mark>:
            pay an invoice to a new bank account, buy gift cards, change payroll details, or share employee records.
          </p>
        </div>
      </foreignObject>

      {/* caption */}
      <foreignObject x="0" y="735" width="1600" height="140" style={{ opacity: caption ? 1 : 0, transition: "opacity .7s", pointerEvents: "none" }}>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "flex-end", height: 140 }}>
          <div style={{ maxWidth: 1400, background: "rgba(23,37,84,.87)", color: "#fff", borderRadius: 16, padding: "14px 32px",
            fontSize: 32, fontWeight: 500, textAlign: "center", lineHeight: 1.3 }}>
            {caption ?? " "}
          </div>
        </div>
      </foreignObject>
    </svg>
  );
}

export default function StoryPlayer({ onDone }: { onDone?: () => void }) {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [run, setRun] = useState(0); // bumped to restart the clock
  const at = useRef(0);
  useEffect(() => {
    if (!playing) return;
    const begin = performance.now() - at.current * 1000;
    let id = 0;
    const tick = (now: number) => {
      at.current = Math.min(END, (now - begin) / 1000);
      setT(at.current);
      if (at.current < END) id = requestAnimationFrame(tick);
      else setPlaying(false);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
  }, [playing, run]);

  const play = () => { if (at.current >= END) { at.current = 0; setT(0); } setRun((n) => n + 1); setPlaying(true); };
  const restart = () => { at.current = 0; setT(0); setPlaying(false); };
  const ended = t >= END;
  const btn = "rounded-lg px-4 py-2 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="relative">
        <Stage t={t} />
        {!playing && t === 0 && (
          <button type="button" onClick={play} aria-label="Play"
            className="absolute inset-0 flex items-end justify-center pb-[3%] focus-visible:outline-none sm:pb-[6%]">
            <span className="flex items-center gap-2 rounded-full bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow-lg hover:bg-blue-700 sm:px-6 sm:py-3 sm:text-base">
              ▶ Play <span className="font-normal text-blue-100">· 45 s</span>
            </span>
          </button>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-slate-100 p-3">
        <button type="button" className={`${btn} bg-blue-600 text-white hover:bg-blue-700`} onClick={() => (playing ? setPlaying(false) : play())}>
          {playing ? "Pause" : ended ? "Play again" : t > 0 ? "Resume" : "Play"}
        </button>
        <button type="button" className={`${btn} border border-slate-300 bg-white text-slate-700 hover:bg-slate-50`} onClick={restart}>Restart</button>
        <div className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-label="Story progress"
          aria-valuemin={0} aria-valuemax={END} aria-valuenow={Math.round(t)}>
          <div className="h-full bg-blue-600" style={{ width: `${(t / END) * 100}%` }} />
        </div>
        {onDone && (
          <button type="button" className={`${btn} ${ended ? "bg-blue-900 text-white" : "text-blue-700 hover:bg-blue-50"}`} onClick={onDone}>
            See how BEC Guard stops it ↓
          </button>
        )}
      </div>
    </div>
  );
}
