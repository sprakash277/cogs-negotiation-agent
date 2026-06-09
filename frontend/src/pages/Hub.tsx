import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowUpRight, FileBarChart, FileText, Swords, BarChart3 } from "lucide-react";
import { api, HubCard, fmtMoney } from "../api";

const accent: Record<string, string> = {
  pepsi: "from-[#004B93] to-[#E32934]",
  coke: "from-[#F40009] to-[#1E1E1E]",
  kdp: "from-[#6B1F2A] to-[#C8102E]",
};

export default function Hub() {
  const [cards, setCards] = useState<HubCard[]>([]);
  const [err, setErr] = useState("");
  const nav = useNavigate();

  useEffect(() => {
    api.hub().then((d) => setCards(d.cards)).catch((e) => setErr(String(e)));
  }, []);

  return (
    <div className="px-10 py-8 max-w-6xl mx-auto">
      <div className="rounded-2xl bg-gradient-to-r from-orange to-rose px-7 py-6 mb-8 shadow-lg">
        <div className="text-[0.65rem] font-extrabold tracking-[0.16em] uppercase text-white/80">
          Kroger Sourcing · Beverages
        </div>
        <h1 className="text-3xl font-extrabold mt-1">COGS Negotiation Hub</h1>
        <p className="text-white/85 mt-1.5 max-w-2xl text-sm">
          Pick a supplier to open its negotiation workspace — auto-built fact-pack deck,
          negotiation brief, scorecard, and a rehearsal room to practice against the vendor.
        </p>
        <div className="flex gap-8 mt-4">
          <Stat n={cards.length} l="open negotiations" />
          <Stat n={cards.filter((c) => c.open_negotiation).length} l="active this cycle" />
          <Stat n={4} l="agent tools" />
        </div>
      </div>

      {err && <div className="text-rose text-sm mb-4">Failed to load: {err}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {cards.map((c) => (
          <div
            key={c.key}
            className="rounded-2xl overflow-hidden border border-white/10 bg-white/[0.03] hover:border-white/25 transition group"
          >
            <div className={`h-20 bg-gradient-to-br ${accent[c.key] ?? "from-teal to-teal-deep"} flex items-end p-4`}>
              <div className="text-lg font-extrabold drop-shadow">{c.supplier}</div>
            </div>
            <div className="p-4">
              <div className="text-[0.7rem] text-white/50">{c.category}</div>
              <div className="flex items-baseline gap-2 mt-2">
                <span className="text-2xl font-extrabold">{fmtMoney(c.annual_spend)}</span>
                <span className="text-[0.7rem] text-white/45">annual spend</span>
              </div>
              <div className="flex items-center gap-1.5 mt-1 text-sm">
                <span className={c.yoy_cogs_change_pct > 0 ? "text-rose" : "text-mint"}>
                  {c.yoy_cogs_change_pct > 0 ? "▲" : "▼"} {Math.abs(c.yoy_cogs_change_pct)}%
                </span>
                <span className="text-[0.7rem] text-white/40">COGS YoY · expires {c.contract_expiry}</span>
              </div>

              <div className="grid grid-cols-2 gap-2 mt-4">
                <Action label="Fact-Pack" icon={FileBarChart} cls="text-cyan" onClick={() => nav(`/deck/${c.key}`)} />
                <Action label="Brief" icon={FileText} cls="text-mint" onClick={() => nav(`/brief/${c.key}`)} />
                <Action label="Scorecard" icon={BarChart3} cls="text-orange" onClick={() => nav(`/scorecard/${c.key}`)} />
                <Action label="Rehearse" icon={Swords} cls="text-purple" onClick={() => nav(`/rehearse/${c.key}`)} />
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className="text-center text-[0.66rem] text-white/30 mt-10">
        Kroger Sourcing · COGS Negotiation Agent · Powered by Databricks
      </div>
    </div>
  );
}

function Stat({ n, l }: { n: number; l: string }) {
  return (
    <div>
      <div className="text-2xl font-extrabold">{n}</div>
      <div className="text-[0.62rem] uppercase tracking-wide text-white/70">{l}</div>
    </div>
  );
}

function Action({ label, icon: Icon, cls, onClick }: any) {
  return (
    <button
      onClick={onClick}
      className="flex items-center justify-between gap-1 px-3 py-2 rounded-lg bg-black/30 border border-white/10 hover:border-white/30 text-xs font-bold transition"
    >
      <span className={`flex items-center gap-1.5 ${cls}`}>
        <Icon size={13} /> {label}
      </span>
      <ArrowUpRight size={12} className="text-white/30" />
    </button>
  );
}
