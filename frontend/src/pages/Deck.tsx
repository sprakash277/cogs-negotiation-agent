import { useState, useEffect, useMemo, useCallback } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, Loader2, Quote, Play, X, ChevronLeft, ChevronRight } from "lucide-react";
import { api, Deck as DeckT, Slide, ChartSpec } from "../api";
import PageHeader from "../components/PageHeader";
import Feedback from "../components/Feedback";

const DEFAULT_OBJ =
  "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle.";

export default function Deck() {
  const { supplier } = useParams();
  const [objective, setObjective] = useState(DEFAULT_OBJ);
  const [deck, setDeck] = useState<DeckT | null>(null);
  const [deckId, setDeckId] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [present, setPresent] = useState(false);

  async function gen() {
    if (!supplier) return;
    setLoading(true); setErr(""); setDeck(null); setDeckId(undefined);
    try {
      const r = await api.deck(supplier, objective);
      setDeck(r.deck);
      setDeckId(r.id);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }

  return (
    <div className="px-10 py-8 max-w-4xl mx-auto">
      <PageHeader kicker="Genie + Deck Builder" title="Fact-Pack & Deck" sub={`Fixed 15-slide, 5-act negotiation deck for ${supplier?.toUpperCase()}`} />

      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <label className="text-[0.66rem] font-bold uppercase tracking-wide text-white/50">Objective</label>
          <input
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className="w-full mt-2 rounded-xl bg-black/30 border border-white/10 focus:border-cyan/60 outline-none p-3 text-sm"
          />
        </div>
        <button
          onClick={gen}
          disabled={loading}
          className="inline-flex items-center gap-2 bg-cyan/90 hover:bg-cyan disabled:opacity-50 text-teal-deep font-extrabold text-sm px-4 py-3 rounded-lg transition"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
          {loading ? "Building…" : "Build deck"}
        </button>
      </div>

      {err && <div className="text-rose text-sm mt-4">{err}</div>}

      {deck && (
        <div className="mt-7 space-y-8">
          {/* hero */}
          <div className="rounded-2xl bg-gradient-to-br from-teal to-teal-deep border border-cyan/25 p-6 relative">
            <button
              onClick={() => setPresent(true)}
              className="absolute top-5 right-5 inline-flex items-center gap-1.5 bg-orange/90 hover:bg-orange text-teal-deep font-extrabold text-xs px-3 py-2 rounded-lg transition"
            >
              <Play size={13} /> Present
            </button>
            <h2 className="text-2xl font-extrabold pr-28">{deck.title}</h2>
            <div className="text-cyan text-sm font-semibold mt-0.5">{deck.subtitle}</div>
            <p className="text-white/80 text-sm mt-3 leading-relaxed border-l-2 border-orange pl-3">
              {deck.objective}
            </p>
            <div className="text-[0.6rem] uppercase tracking-wide text-white/40 mt-3">{deck.format_version}</div>
          </div>

          {deck.acts?.map((act, ai) => (
            <div key={ai} className="space-y-4">
              {/* act header */}
              <div className="flex items-center gap-3">
                <div className="text-[0.62rem] font-extrabold uppercase tracking-widest text-orange bg-orange/10 border border-orange/30 rounded-full px-3 py-1">
                  Act {ai + 1}
                </div>
                <h3 className="text-lg font-extrabold text-white/90">{act.act}</h3>
                <div className="flex-1 h-px bg-white/10" />
              </div>

              {act.slides?.map((s) => <SlideCard key={s.slide_no} s={s} />)}
            </div>
          ))}

          <Feedback artifactId={deckId} kind="decks" supplierKey={supplier} />
        </div>
      )}

      {present && deck && <PresentMode deck={deck} onExit={() => setPresent(false)} />}
    </div>
  );
}

// --- Present mode: same deck JSON rendered as 16:9 navigable slides -------- #
type Screen =
  | { kind: "title" }
  | { kind: "content"; actLabel: string; actNo: number; slide: Slide };

function PresentMode({ deck, onExit }: { deck: DeckT; onExit: () => void }) {
  const screens = useMemo<Screen[]>(() => {
    const out: Screen[] = [{ kind: "title" }];
    deck.acts?.forEach((act, ai) =>
      act.slides?.forEach((slide) =>
        out.push({ kind: "content", actLabel: act.act, actNo: ai + 1, slide })
      )
    );
    return out;
  }, [deck]);

  const total = screens.length;
  const [i, setI] = useState(0);
  const go = useCallback(
    (d: number) => setI((p) => Math.min(total - 1, Math.max(0, p + d))),
    [total]
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (["ArrowRight", " ", "PageDown"].includes(e.key)) { e.preventDefault(); go(1); }
      else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); go(-1); }
      else if (e.key === "Escape") onExit();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onExit]);

  const cur = screens[i];
  return (
    <div className="fixed inset-0 z-50 bg-teal-deep flex flex-col">
      {/* top bar */}
      <div className="flex items-center justify-between px-6 py-3 text-white/70 shrink-0">
        <div className="text-[0.66rem] font-extrabold uppercase tracking-widest">
          {deck.supplier} · Negotiation Deck
        </div>
        <div className="flex items-center gap-5">
          <span className="text-xs font-mono text-white/50">{i + 1} / {total}</span>
          <button onClick={onExit} className="inline-flex items-center gap-1 text-xs font-bold hover:text-white transition">
            <X size={14} /> Exit
          </button>
        </div>
      </div>

      {/* slide stage */}
      <div className="flex-1 flex items-center justify-center px-14 pb-6 min-h-0">
        <div className="w-full max-w-6xl aspect-video bg-gradient-to-br from-teal to-teal-deep border border-cyan/25 rounded-2xl shadow-2xl p-10 overflow-hidden relative">
          {cur.kind === "title"
            ? <TitleSlide deck={deck} />
            : <ContentSlide actLabel={cur.actLabel} actNo={cur.actNo} s={cur.slide} />}
          <div className="absolute bottom-4 right-6 text-[0.55rem] text-white/30 uppercase tracking-widest">
            {deck.format_version}
          </div>
        </div>
      </div>

      {/* nav arrows */}
      <button
        onClick={() => go(-1)} disabled={i === 0}
        className="fixed left-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/5 hover:bg-white/15 disabled:opacity-20 transition"
        aria-label="Previous slide"
      >
        <ChevronLeft size={22} />
      </button>
      <button
        onClick={() => go(1)} disabled={i === total - 1}
        className="fixed right-3 top-1/2 -translate-y-1/2 p-2 rounded-full bg-white/5 hover:bg-white/15 disabled:opacity-20 transition"
        aria-label="Next slide"
      >
        <ChevronRight size={22} />
      </button>

      {/* progress dots */}
      <div className="flex items-center justify-center gap-1.5 pb-4 shrink-0">
        {screens.map((_, idx) => (
          <button
            key={idx}
            onClick={() => setI(idx)}
            className={`h-1.5 rounded-full transition-all ${idx === i ? "w-5 bg-orange" : "w-1.5 bg-white/25 hover:bg-white/50"}`}
            aria-label={`Go to slide ${idx + 1}`}
          />
        ))}
      </div>
    </div>
  );
}

function TitleSlide({ deck }: { deck: DeckT }) {
  return (
    <div className="h-full flex flex-col justify-center">
      <div className="text-[0.7rem] font-extrabold uppercase tracking-[0.2em] text-cyan">{deck.supplier}</div>
      <h1 className="text-5xl font-extrabold mt-4 leading-tight">{deck.title}</h1>
      <div className="text-lg text-cyan font-semibold mt-3">{deck.subtitle}</div>
      <p className="text-white/80 text-base mt-6 leading-relaxed border-l-2 border-orange pl-4 max-w-3xl">
        {deck.objective}
      </p>
    </div>
  );
}

function ContentSlide({ actLabel, actNo, s }: { actLabel: string; actNo: number; s: Slide }) {
  const hasChart = !!(s.chart && s.chart.kind !== "none" && s.chart.series?.length);
  const hasRight = (s.data_callouts?.length || 0) > 0 || hasChart;
  return (
    <div className="h-full flex flex-col min-h-0">
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-[0.6rem] font-extrabold uppercase tracking-widest text-orange bg-orange/10 border border-orange/30 rounded-full px-3 py-1">
          Act {actNo} · {actLabel}
        </span>
        <span className="text-cyan font-extrabold text-sm">{String(s.slide_no).padStart(2, "0")}</span>
      </div>
      <h2 className="text-3xl font-extrabold mt-3 shrink-0">{s.title}</h2>
      <div className="text-base font-bold text-orange mt-2 border-l-2 border-orange pl-3 shrink-0">{s.headline}</div>

      <div className={`flex-1 mt-5 grid gap-6 min-h-0 ${hasRight ? "grid-cols-2" : "grid-cols-1"}`}>
        <div className="overflow-auto pr-1">
          {s.narrative && <p className="text-white/85 text-sm leading-relaxed">{s.narrative}</p>}
          {s.bullets?.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {s.bullets.map((b, i) => (
                <li key={i} className="flex gap-2 text-sm text-white/80">
                  <span className="text-cyan font-extrabold">•</span> {b}
                </li>
              ))}
            </ul>
          )}
          {s.citations?.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {s.citations.map((c, i) => (
                <span key={i} className="inline-flex items-center gap-1 text-[0.62rem] text-mint bg-mint/10 border border-mint/25 rounded-full px-2 py-0.5">
                  <Quote size={9} /> {c}
                </span>
              ))}
            </div>
          )}
        </div>

        {hasRight && (
          <div className="overflow-auto space-y-4">
            {s.data_callouts?.length > 0 && (
              <div className="grid grid-cols-2 gap-3">
                {s.data_callouts.map((c, i) => (
                  <div key={i} className="rounded-xl border border-white/10 bg-white/[0.05] p-3">
                    <div className="text-[0.58rem] uppercase tracking-wide text-white/45">{c.label}</div>
                    <div className="text-xl font-extrabold mt-0.5">{c.value}</div>
                    {c.delta && <div className="text-xs font-bold text-cyan mt-0.5">{c.delta}</div>}
                    <div className="text-[0.52rem] text-white/35 mt-1 font-mono truncate" title={c.source}>{c.source}</div>
                  </div>
                ))}
              </div>
            )}
            {hasChart && <Chart spec={s.chart!} />}
          </div>
        )}
      </div>
    </div>
  );
}

function SlideCard({ s }: { s: Slide }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
      <div className="flex items-baseline gap-2">
        <span className="text-cyan font-extrabold text-sm">{String(s.slide_no).padStart(2, "0")}</span>
        <h4 className="text-base font-extrabold">{s.title}</h4>
      </div>
      <div className="mt-2 text-sm font-bold text-orange border-l-2 border-orange/60 pl-3">{s.headline}</div>
      {s.narrative && <p className="text-white/80 text-sm mt-3 leading-relaxed">{s.narrative}</p>}

      {s.bullets?.length > 0 && (
        <ul className="mt-3 space-y-1.5">
          {s.bullets.map((b, i) => (
            <li key={i} className="flex gap-2 text-sm text-white/80">
              <span className="text-cyan font-extrabold">•</span> {b}
            </li>
          ))}
        </ul>
      )}

      {s.data_callouts?.length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
          {s.data_callouts.map((c, i) => (
            <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="text-[0.6rem] uppercase tracking-wide text-white/45">{c.label}</div>
              <div className="text-lg font-extrabold mt-0.5">{c.value}</div>
              {c.delta && <div className="text-xs font-bold text-cyan mt-0.5">{c.delta}</div>}
              <div className="text-[0.55rem] text-white/35 mt-1 font-mono truncate" title={c.source}>{c.source}</div>
            </div>
          ))}
        </div>
      )}

      {s.chart && s.chart.kind !== "none" && s.chart.series?.length > 0 && (
        <div className="mt-4"><Chart spec={s.chart} /></div>
      )}

      {s.citations?.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {s.citations.map((c, i) => (
            <span key={i} className="inline-flex items-center gap-1 text-[0.62rem] text-mint bg-mint/10 border border-mint/25 rounded-full px-2 py-0.5">
              <Quote size={9} /> {c}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Lightweight CSS/SVG charts (no chart dependency) ---------------------- #
const PALETTE = ["#22D3EE", "#FF6F3C", "#64FFDA", "#A78BFA", "#FB7185", "#FFB454", "#5CC8FF"];

function numFrom(row: Record<string, any>): number {
  // Pick the first numeric-looking value in the row.
  for (const v of Object.values(row)) {
    const n = typeof v === "number" ? v : parseFloat(v);
    if (!Number.isNaN(n)) return n;
  }
  return 0;
}

function labelFrom(row: Record<string, any>, fallback: string): string {
  for (const v of Object.values(row)) {
    if (typeof v === "string" && Number.isNaN(parseFloat(v))) return v;
  }
  return fallback;
}

function Chart({ spec }: { spec: ChartSpec }) {
  if (spec.kind === "line") return <LineChart series={spec.series} />;
  // waterfall / bridge / bars / scenario all render as a labeled bar chart.
  return <BarChart series={spec.series} stacked={spec.kind === "waterfall" || spec.kind === "scenario"} />;
}

function BarChart({ series, stacked }: { series: Record<string, any>[]; stacked: boolean }) {
  const vals = series.map(numFrom);
  const max = Math.max(...vals, 1);
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3 space-y-2">
      {series.map((row, i) => {
        const v = vals[i];
        const label = labelFrom(row, `#${i + 1}`);
        return (
          <div key={i} className="flex items-center gap-2">
            <div className="w-28 shrink-0 text-[0.62rem] text-white/60 truncate" title={label}>{label}</div>
            <div className="flex-1 h-4 rounded bg-white/5 overflow-hidden">
              <div
                className="h-full rounded"
                style={{ width: `${Math.max(2, (Math.abs(v) / max) * 100)}%`, background: PALETTE[i % PALETTE.length] }}
              />
            </div>
            <div className="w-16 shrink-0 text-right text-[0.66rem] font-mono text-white/70">{v}</div>
          </div>
        );
      })}
      {stacked && <div className="text-[0.55rem] text-white/30 uppercase tracking-wide">components</div>}
    </div>
  );
}

function LineChart({ series }: { series: Record<string, any>[] }) {
  const vals = series.map(numFrom);
  if (vals.length < 2) return <BarChart series={series} stacked={false} />;
  const max = Math.max(...vals);
  const min = Math.min(...vals);
  const range = max - min || 1;
  const W = 520, H = 120, pad = 8;
  const pts = vals.map((v, i) => {
    const x = pad + (i / (vals.length - 1)) * (W - 2 * pad);
    const y = H - pad - ((v - min) / range) * (H - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28">
        <polyline points={pts.join(" ")} fill="none" stroke="#22D3EE" strokeWidth="2" />
        {vals.map((_, i) => {
          const [x, y] = pts[i].split(",");
          return <circle key={i} cx={x} cy={y} r="2" fill="#FF6F3C" />;
        })}
      </svg>
      <div className="flex justify-between text-[0.58rem] text-white/40 font-mono mt-1">
        <span>{min}</span><span>{max}</span>
      </div>
    </div>
  );
}
