import StoryPlayer from "../components/StoryPlayer";

const WAYS = [
  {
    title: "A stranger pretends to be someone you pay",
    text: "A lookalike address (acmesuppIy.com), a copied name, or a company you've never paid. BEC Guard checks the sender against your records and the company's official website.",
  },
  {
    title: "Your vendor's real mailbox is hacked",
    text: "Every sender check passes, because it really is their address. BEC Guard compares the bank details, even inside a PDF, with the account you've always paid.",
  },
  {
    title: "Your own mailbox is hacked",
    text: "Hidden filters, payment emails sent from your account, sent mail deleted. BEC Guard watches your mailbox for these and alerts your compliance team.",
  },
];

const STEPS = [
  { who: "Nemotron Nano", what: "Is this email asking for money or data? Most email stops here, fast and cheap." },
  { who: "Rules + your records", what: "Sender, address lookalikes, bank account and amount compared with the vendor records." },
  { who: "Nemotron Super agent + web search", what: "Finds the company's official website and phone number, and checks the email against them." },
  { who: "Nemotron Super and Super VL", what: "Pressure and secrecy in the wording, the writing style, and bank details inside PDFs." },
  { who: "Rules decide", what: "Verify before paying, Looks unusual, or No issues found. A model never makes the decision." },
  { who: "Nemotron Ultra", what: "Explains why in plain words. Code rejects any rewrite that changes an address or a number." },
];

export default function Home() {
  return (
    <main>
      <section className="mx-auto max-w-5xl px-4 pt-10 pb-12">
        <p className="text-sm font-semibold uppercase tracking-wide text-blue-600">Business email compromise</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">
          One email. One wrong bank account. The money is gone.
        </h2>
        <p className="mt-3 text-slate-600">
          Business email compromise cost victims <strong className="text-slate-900">$3 billion</strong> in 2025,
          second only to investment fraud{" "}
          <a href="https://www.ic3.gov/AnnualReport/Reports/2025_IC3Report.pdf" target="_blank" rel="noreferrer"
            className="text-sm text-blue-700 underline">(FBI Internet Crime Report 2025, p. 8)</a>.
          Watch how one payment scam happens, then see how BEC Guard stops it.
        </p>
        <div className="mt-6">
          <StoryPlayer onDone={() => document.getElementById("ways")?.scrollIntoView({ behavior: "smooth" })} />
        </div>
      </section>

      <section aria-labelledby="ways" className="scroll-mt-16 border-y border-slate-200 bg-white">
        <div className="mx-auto max-w-6xl px-4 py-12">
          <h2 id="ways" className="text-2xl font-semibold">How BEC Guard stops it</h2>
          <p className="mt-2 max-w-3xl text-slate-600">
            BEC Guard sits inside Gmail. It checks every email that asks for money or data, before anyone pays, and
            covers the three ways the money gets stolen.
          </p>
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {WAYS.map((w, i) => (
              <li key={w.title} className="rounded-xl border border-slate-200 p-5">
                <span className="flex size-8 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700">{i + 1}</span>
                <h3 className="mt-3 font-semibold">{w.title}</h3>
                <p className="mt-1 text-sm text-slate-600">{w.text}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="how" aria-labelledby="how-title" className="mx-auto max-w-6xl scroll-mt-20 px-4 py-12">
        <h2 id="how-title" className="text-2xl font-semibold">How it works</h2>
        <p className="mt-2 max-w-3xl text-slate-600">
          Every new email is checked within about a minute of arriving. The result appears as a card next to the email,
          and risky emails get a label in the inbox. All models run on Nebius Token Factory.
        </p>
        <ol className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {STEPS.map((st, i) => (
            <li key={st.who} className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4">
              <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">{i + 1}</span>
              <div>
                <div className="font-medium">{st.who}</div>
                <p className="mt-0.5 text-sm text-slate-600">{st.what}</p>
              </div>
            </li>
          ))}
        </ol>
        <div className="mt-8 flex flex-wrap items-center gap-3 rounded-xl bg-blue-600 p-5 text-white">
          <p className="flex-1 text-sm sm:text-base">Open the sample inbox, or write your own scam email and see what BEC Guard says.</p>
          <a href="#try" className="rounded-lg bg-white px-5 py-2.5 text-sm font-medium text-blue-700 hover:bg-blue-50">Try it</a>
          <a href="#production" className="rounded-lg border border-white/60 px-5 py-2.5 text-sm font-medium text-white hover:bg-white/10">From demo to product</a>
        </div>
      </section>
    </main>
  );
}
