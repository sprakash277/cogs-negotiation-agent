import { useState } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, Loader2 } from "lucide-react";
import { api, Deck as DeckT } from "../api";
import PageHeader from "../components/PageHeader";

const DEFAULT_OBJ =
  "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle.";

const toneColor: Record<string, string> = {
  good: "text-mint", bad: "text-rose", neutral: "text-cyan",
};

export default function Deck() {
  const { supplier } = useParams();
  const [objective, setObjective] = useState(DEFAULT_OBJ);
  const [deck, setDeck] = useState<DeckT | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function gen() {
    if (!supplier) return;
    setLoading(true); setErr(""); setDeck(null);
    try {
      const r = await api.deck(supplier, objective);
      setDeck(r.deck);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }

  return (
    <div className="px-10 py-8 max-w-4xl mx-auto">
      <PageHeader kicker="Genie + Deck Builder" title="Fact-Pack & Deck" sub={`Auto-built negotiation deck for ${supplier?.toUpperCase()}`} />

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
        <div className="mt-7 space-y-6">
          {/* hero */}
          <div className="rounded-2xl bg-gradient-to-br from-teal to-teal-deep border border-cyan/25 p-6">
            <h2 className="text-2xl font-extrabold">{deck.title}</h2>
            <div className="text-cyan text-sm font-semibold mt-0.5">{deck.subtitle}</div>
            <p className="text-white/80 text-sm mt-3 leading-relaxed border-l-2 border-orange pl-3">
              {deck.hypothesis}
            </p>
          </div>

          {/* kpis */}
          {deck.kpis?.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {deck.kpis.map((k, i) => (
                <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
                  <div className="text-[0.62rem] uppercase tracking-wide text-white/45">{k.label}</div>
                  <div className="text-2xl font-extrabold mt-1">{k.value}</div>
                  <div className={`text-xs font-bold mt-0.5 ${toneColor[k.tone] ?? "text-white/60"}`}>{k.delta}</div>
                </div>
              ))}
            </div>
          )}

          {/* sections */}
          {deck.sections?.map((s, i) => (
            <div key={i} className="rounded-2xl border border-white/10 bg-white/[0.02] p-5">
              <h3 className="text-lg font-extrabold">{s.heading}</h3>
              <p className="text-white/80 text-sm mt-2 leading-relaxed">{s.narrative}</p>
              <div className="mt-3 text-sm font-bold text-orange border-l-2 border-orange/60 pl-3">{s.callout}</div>
            </div>
          ))}

          {/* asks */}
          {deck.asks?.length > 0 && (
            <div className="rounded-2xl border border-mint/25 bg-mint/[0.04] p-5">
              <h3 className="text-sm font-extrabold uppercase tracking-wide text-mint">Negotiation Asks</h3>
              <ul className="mt-3 space-y-2">
                {deck.asks.map((a, i) => (
                  <li key={i} className="flex gap-2 text-sm text-white/85">
                    <span className="text-mint font-extrabold">{i + 1}.</span> {a}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
