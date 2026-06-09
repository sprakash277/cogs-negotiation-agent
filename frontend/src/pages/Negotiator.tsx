import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Compass, Database, ChevronDown, ChevronRight } from "lucide-react";
import { api, SupervisorResult } from "../api";
import PageHeader from "../components/PageHeader";

interface Turn {
  role: "user" | "assistant";
  content?: string;
  result?: SupervisorResult;
}

const routeStyle: Record<string, string> = {
  scorecard: "text-orange border-orange/40",
  brief: "text-mint border-mint/40",
  deck: "text-cyan border-cyan/40",
  rehearse: "text-purple border-purple/40",
  chat: "text-white/60 border-white/20",
};

const EXAMPLES = [
  "Which supplier has the worst OTIF?",
  "Draft a brief for Pepsi to claw back COGS inflation",
  "Build a fact-pack deck for Coca-Cola",
  "Let's rehearse negotiating with Keurig Dr Pepper",
];

export default function Negotiator() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [turns, loading]);

  async function send(text?: string) {
    const msg = (text ?? input).trim();
    if (!msg || loading) return;
    setInput("");
    // history for rehearsal continuity: buyer = user, vendor = assistant
    const history = turns
      .filter((t) => t.content || t.result?.answer)
      .map((t) => ({ role: t.role === "user" ? "buyer" : "vendor", content: t.content ?? t.result?.answer ?? "" }));
    setTurns((p) => [...p, { role: "user", content: msg }]);
    setLoading(true);
    try {
      const r = await api.supervisorAsk(msg, history);
      setTurns((p) => [...p, { role: "assistant", result: r }]);
    } catch (e) {
      setTurns((p) => [...p, { role: "assistant", result: { route: "chat", answer: `Error: ${e}` } }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="px-10 py-8 max-w-3xl mx-auto flex flex-col h-full">
      <PageHeader
        kicker="Multi-Agent Supervisor · routes to the right sub-agent"
        title="Negotiator"
        sub="Ask anything — the supervisor routes to Genie, the brief writer, the deck builder, or the rehearsal room."
      />

      <div className="flex-1 overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.02] p-5 space-y-4">
        {turns.length === 0 && (
          <div className="text-center text-white/45 text-sm py-8">
            <Compass size={28} className="mx-auto mb-3 text-orange" />
            One box, all four agents. Try:
            <div className="flex flex-col items-center gap-2 mt-4">
              {EXAMPLES.map((e) => (
                <button key={e} onClick={() => send(e)}
                  className="text-[0.8rem] text-white/80 bg-black/30 border border-white/10 hover:border-orange/40 rounded-full px-3 py-1.5 transition">
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}

        {turns.map((t, i) => (
          <div key={i} className={`flex ${t.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm ${
              t.role === "user" ? "bg-orange/20 border border-orange/40" : "bg-white/[0.03] border border-white/10"
            }`}>
              {t.role === "user" ? t.content : <AssistantBubble r={t.result!} />}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-white/[0.03] border border-white/10 rounded-2xl px-4 py-3 text-sm">
              <Loader2 size={14} className="animate-spin inline" /> supervisor is routing…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="flex gap-2 mt-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask the negotiator anything…"
          className="flex-1 rounded-xl bg-black/30 border border-white/10 focus:border-orange/60 outline-none px-4 py-3 text-sm"
        />
        <button onClick={() => send()} disabled={loading}
          className="bg-orange hover:bg-orange-light disabled:opacity-50 text-white font-extrabold px-4 rounded-xl transition">
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}

function AssistantBubble({ r }: { r: SupervisorResult }) {
  const [showSql, setShowSql] = useState(false);
  return (
    <div>
      <div className={`inline-block text-[0.55rem] font-extrabold uppercase tracking-wide mb-2 px-2 py-0.5 rounded-full border ${routeStyle[r.route]}`}>
        {r.route}{r.supplier ? ` · ${r.supplier}` : ""}
      </div>
      {r.answer && <div className="whitespace-pre-wrap leading-relaxed text-white/90">{r.answer}</div>}

      {r.rows && r.rows.length > 0 && r.columns && (
        <div className="mt-3 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full text-[0.8rem]">
            <thead><tr className="text-left text-[0.58rem] uppercase tracking-wide text-white/45 border-b border-white/10">
              {r.columns.map((c) => <th key={c} className="px-2.5 py-2 whitespace-nowrap">{c}</th>)}
            </tr></thead>
            <tbody>
              {r.rows.map((row, i) => (
                <tr key={i} className="border-b border-white/5">
                  {row.map((cell, j) => <td key={j} className="px-2.5 py-1.5 text-white/80 whitespace-nowrap">{cell}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {r.deck && (
        <div className="mt-3 rounded-xl border border-cyan/25 bg-cyan/[0.04] p-3">
          <div className="font-extrabold text-cyan">{r.deck.title}</div>
          <div className="text-[0.75rem] text-white/70 mt-1">{r.deck.hypothesis}</div>
          {r.deck.kpis?.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mt-3">
              {r.deck.kpis.map((k, i) => (
                <div key={i} className="bg-black/30 rounded-lg p-2 text-center">
                  <div className="text-[0.55rem] uppercase text-white/45">{k.label}</div>
                  <div className="font-extrabold text-sm">{k.value}</div>
                  <div className="text-[0.6rem] text-white/60">{k.delta}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {r.sql && (
        <div className="mt-2">
          <button onClick={() => setShowSql((s) => !s)} className="flex items-center gap-1 text-[0.66rem] text-cyan/80 hover:text-cyan">
            {showSql ? <ChevronDown size={12} /> : <ChevronRight size={12} />}<Database size={11} /> SQL
          </button>
          {showSql && <pre className="mt-1 text-[0.66rem] text-white/60 bg-black/40 border border-white/10 rounded-lg p-2 overflow-x-auto whitespace-pre-wrap">{r.sql}</pre>}
        </div>
      )}
    </div>
  );
}
