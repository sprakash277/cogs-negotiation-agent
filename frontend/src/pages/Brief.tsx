import { useState } from "react";
import { useParams } from "react-router-dom";
import { Sparkles, Loader2, FileText } from "lucide-react";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

const DEFAULT_OBJ =
  "Reduce landed COGS and improve trade-fund efficiency for the upcoming contract cycle.";

export default function Brief() {
  const { supplier } = useParams();
  const [objective, setObjective] = useState(DEFAULT_OBJ);
  const [content, setContent] = useState("");
  const [sources, setSources] = useState<{ section: string; supplier: string }[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  async function gen() {
    if (!supplier) return;
    setLoading(true); setErr(""); setContent(""); setSources([]);
    try {
      const r = await api.brief(supplier, objective);
      setContent(r.content);
      setSources(r.sources || []);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }

  return (
    <div className="px-10 py-8 max-w-4xl mx-auto">
      <PageHeader kicker="Knowledge Assistant · RAG over contract MSAs" title="Negotiation Brief" sub={`Grounded talking points for ${supplier?.toUpperCase()}`} />

      <label className="text-[0.66rem] font-bold uppercase tracking-wide text-white/50">Negotiation objective</label>
      <textarea
        value={objective}
        onChange={(e) => setObjective(e.target.value)}
        rows={2}
        className="w-full mt-2 rounded-xl bg-black/30 border border-white/10 focus:border-orange/60 outline-none p-3 text-sm resize-none"
      />
      <button
        onClick={gen}
        disabled={loading}
        className="mt-3 inline-flex items-center gap-2 bg-orange hover:bg-orange-light disabled:opacity-50 text-white font-bold text-sm px-4 py-2.5 rounded-lg transition"
      >
        {loading ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}
        {loading ? "Drafting…" : "Generate brief"}
      </button>

      {err && <div className="text-rose text-sm mt-4">{err}</div>}

      {sources.length > 0 && (
        <div className="mt-5 rounded-xl border border-mint/25 bg-mint/[0.04] p-3">
          <div className="flex items-center gap-1.5 text-[0.66rem] font-extrabold uppercase tracking-wide text-mint">
            <FileText size={12} /> Grounded in contract clauses (Vector Search)
          </div>
          <div className="flex flex-wrap gap-2 mt-2">
            {sources.map((s, i) => (
              <span key={i} className="text-[0.68rem] bg-black/30 border border-mint/30 rounded-full px-2.5 py-1 text-white/80">
                {s.section}
              </span>
            ))}
          </div>
        </div>
      )}

      {content && (
        <div className="mt-5 rounded-2xl border border-white/10 bg-white/[0.02] p-6 whitespace-pre-wrap text-sm leading-relaxed text-white/90">
          {content}
        </div>
      )}
    </div>
  );
}
