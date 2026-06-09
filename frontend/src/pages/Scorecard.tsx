import { useEffect, useState } from "react";
import { Sparkles, Loader2, Database, ChevronDown, ChevronRight, Table2, BarChart3, ExternalLink } from "lucide-react";
import { api, GenieResult } from "../api";
import PageHeader from "../components/PageHeader";

export default function Scorecard() {
  const [tab, setTab] = useState<"table" | "dashboard">("table");
  const [data, setData] = useState<GenieResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [dash, setDash] = useState<{ embed_url: string; full_url: string } | null>(null);

  // free-form Ask Genie
  const [q, setQ] = useState("");
  const [ask, setAsk] = useState<GenieResult | null>(null);
  const [asking, setAsking] = useState(false);
  const [convId, setConvId] = useState<string | undefined>();

  useEffect(() => {
    setLoading(true);
    api.genieScorecard()
      .then((d) => setData(d))
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
    api.dashboard().then(setDash).catch(() => {});
  }, []);

  async function runAsk() {
    if (!q.trim() || asking) return;
    setAsking(true);
    try {
      const r = await api.genieAsk(q, convId);
      setAsk(r);
      if (r.conversation_id) setConvId(r.conversation_id);
    } catch (e) {
      setAsk({ text: String(e), sql: null, columns: [], rows: [] });
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="px-10 py-8 max-w-6xl mx-auto">
      <PageHeader
        kicker="Genie + AI/BI · live over Unity Catalog"
        title="Supplier Scorecard"
        sub="Sourced live from kroger_demo.cogs — conversational table via Genie, plus the AI/BI dashboard."
      />

      {/* Tabs */}
      <div className="flex gap-2 mb-5">
        <button onClick={() => setTab("table")}
          className={`flex items-center gap-1.5 text-sm font-bold px-3 py-1.5 rounded-lg border transition ${tab === "table" ? "border-orange/50 bg-orange/15 text-white" : "border-white/10 text-white/55 hover:text-white"}`}>
          <Table2 size={14} /> Live Table (Genie)
        </button>
        <button onClick={() => setTab("dashboard")}
          className={`flex items-center gap-1.5 text-sm font-bold px-3 py-1.5 rounded-lg border transition ${tab === "dashboard" ? "border-cyan/50 bg-cyan/15 text-white" : "border-white/10 text-white/55 hover:text-white"}`}>
          <BarChart3 size={14} /> AI/BI Dashboard
        </button>
      </div>

      {tab === "dashboard" ? (
        <div>
          {dash && (
            <a href={dash.full_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-[0.72rem] text-cyan hover:text-cyan/80 mb-2">
              <ExternalLink size={12} /> Open full dashboard in Databricks
            </a>
          )}
          <div className="rounded-2xl border border-white/10 overflow-hidden bg-white/[0.02]" style={{ height: 760 }}>
            {dash ? (
              <iframe title="AI/BI Dashboard" src={dash.embed_url} className="w-full h-full" style={{ border: 0 }} />
            ) : (
              <Loading label="loading dashboard…" />
            )}
          </div>
          <div className="text-[0.66rem] text-white/35 mt-2">
            If the embed is blank, the workspace must approve this app's domain for AI/BI embedding — use the link above meanwhile.
          </div>
        </div>
      ) : (
        <>
      {loading && <Loading label="Genie is querying Unity Catalog…" />}
      {err && <div className="text-rose text-sm mb-4">Failed: {err}</div>}
      {data && <GenieTable result={data} />}

      {/* Ask Genie panel */}
      <div className="mt-8 rounded-2xl border border-cyan/25 bg-cyan/[0.03] p-5">
        <div className="flex items-center gap-2 text-cyan font-extrabold text-sm">
          <Sparkles size={16} /> Ask Genie
        </div>
        <p className="text-white/50 text-xs mt-1">
          Ask anything about beverage-supplier COGS in plain English. Genie writes the SQL.
        </p>
        <div className="flex gap-2 mt-3">
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && runAsk()}
            placeholder="e.g. Which supplier has the worst OTIF and how does its trade spend compare?"
            className="flex-1 rounded-xl bg-black/30 border border-white/10 focus:border-cyan/60 outline-none px-4 py-3 text-sm"
          />
          <button
            onClick={runAsk}
            disabled={asking}
            className="bg-cyan/90 hover:bg-cyan disabled:opacity-50 text-teal-deep font-extrabold px-4 rounded-xl transition"
          >
            {asking ? <Loader2 size={16} className="animate-spin" /> : "Ask"}
          </button>
        </div>
        {ask && (
          <div className="mt-4">
            {ask.text && <div className="text-sm text-white/90 leading-relaxed mb-3">{ask.text}</div>}
            <GenieTable result={ask} compact />
          </div>
        )}
      </div>
        </>
      )}
    </div>
  );
}

function Loading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 text-white/50 text-sm py-10 justify-center">
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  );
}

function GenieTable({ result, compact }: { result: GenieResult; compact?: boolean }) {
  const [showSql, setShowSql] = useState(false);
  if (!result.columns.length && !result.rows.length) {
    return result.text ? null : <div className="text-white/40 text-sm">No tabular result.</div>;
  }
  return (
    <div>
      <div className="overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.02]">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[0.62rem] uppercase tracking-wide text-white/45 border-b border-white/10">
              {result.columns.map((c) => (
                <th key={c} className="px-3 py-3 font-bold whitespace-nowrap">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row, i) => (
              <tr key={i} className="border-b border-white/5 hover:bg-white/[0.03]">
                {row.map((cell, j) => (
                  <td key={j} className="px-3 py-2.5 text-white/80 whitespace-nowrap">{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {result.sql && (
        <div className="mt-2">
          <button
            onClick={() => setShowSql((s) => !s)}
            className="flex items-center gap-1 text-[0.7rem] text-cyan/80 hover:text-cyan"
          >
            {showSql ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
            <Database size={12} /> {showSql ? "Hide" : "Show"} generated SQL
          </button>
          {showSql && (
            <pre className="mt-2 text-[0.68rem] text-white/60 bg-black/40 border border-white/10 rounded-xl p-3 overflow-x-auto whitespace-pre-wrap">
              {result.sql}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
