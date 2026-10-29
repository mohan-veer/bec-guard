import { useEffect, useState } from "react";
import { fetchHealth } from "./api";
import ModelRouting from "./components/ModelRouting";
import Home from "./pages/Home";
import Production from "./pages/Production";
import TryIt from "./pages/TryIt";

type Page = "home" | "try" | "production";
const PAGES: { id: Page; label: string }[] = [
  { id: "home", label: "Home" },
  { id: "try", label: "Try it" },
  { id: "production", label: "Production" },
];

// The URL hash is the page (#try), so links and the browser's back button work without a router.
const fromHash = (): Page => PAGES.find((p) => `#${p.id}` === window.location.hash)?.id ?? "home";

export default function App() {
  const [page, setPage] = useState<Page>(fromHash);
  const [mode, setMode] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => { setPage(fromHash()); window.scrollTo(0, 0); };
    window.addEventListener("hashchange", onHash);
    fetchHealth().then((h) => setMode(h.llm_mode === "real" ? "Live models" : "Mock mode")).catch(() => setMode(null));
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-3">
          <a href="#home" className="flex items-center gap-3">
            <span aria-hidden className="flex size-8 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">BG</span>
            <div>
              <h1 className="text-base font-semibold leading-tight">BEC Guard</h1>
              <p className="hidden text-xs text-slate-500 sm:block">Checks payment requests in email before you pay</p>
            </div>
          </a>
          <nav aria-label="Sections" className="flex gap-1 rounded-lg bg-slate-100 p-1">
            {PAGES.map((p) => (
              <a key={p.id} href={`#${p.id}`} aria-current={page === p.id ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:outline-blue-600 ${
                  page === p.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900"
                }`}>
                {p.label}
              </a>
            ))}
          </nav>
          <div className="flex items-center gap-2">
            {mode && <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-600">{mode}</span>}
            <ModelRouting />
          </div>
        </div>
      </header>

      {page === "home" && <Home />}
      {page === "try" && <TryIt />}
      {page === "production" && <Production />}
    </div>
  );
}
