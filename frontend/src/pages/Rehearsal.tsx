import { useState, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import { Send, Loader2, Swords } from "lucide-react";
import { api } from "../api";
import PageHeader from "../components/PageHeader";

interface Msg { role: "buyer" | "vendor"; content: string; }

export default function Rehearsal() {
  const { supplier } = useParams();
  const [history, setHistory] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [history, loading]);

  async function send() {
    if (!input.trim() || !supplier || loading) return;
    const msg = input.trim();
    setInput("");
    const next = [...history, { role: "buyer" as const, content: msg }];
    setHistory(next);
    setLoading(true);
    try {
      const r = await api.rehearse(supplier, msg, history);
      setHistory([...next, { role: "vendor", content: r.reply }]);
    } catch (e) {
      setHistory([...next, { role: "vendor", content: `[error: ${e}]` }]);
    } finally { setLoading(false); }
  }

  return (
    <div className="px-10 py-8 max-w-3xl mx-auto flex flex-col h-full">
      <PageHeader kicker="Vendor Rehearsal Agent" title="Rehearsal Room" sub={`Practice against the ${supplier?.toUpperCase()} key account manager`} />

      <div className="flex-1 overflow-y-auto rounded-2xl border border-white/10 bg-white/[0.02] p-5 space-y-4">
        {history.length === 0 && (
          <div className="text-center text-white/40 text-sm py-12">
            <Swords size={28} className="mx-auto mb-3 text-purple" />
            Open with your first move — the vendor will push back. Practice your concession ladder.
          </div>
        )}
        {history.map((m, i) => (
          <div key={i} className={`flex ${m.role === "buyer" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[78%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              m.role === "buyer"
                ? "bg-orange/20 border border-orange/40"
                : "bg-purple/10 border border-purple/35"
            }`}>
              <div className="text-[0.6rem] font-extrabold uppercase tracking-wide mb-1 opacity-60">
                {m.role === "buyer" ? "You (Kroger)" : `${supplier?.toUpperCase()} KAM`}
              </div>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-purple/10 border border-purple/35 rounded-2xl px-4 py-2.5 text-sm">
              <Loader2 size={14} className="animate-spin inline" /> vendor is responding…
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
          placeholder="Make your offer…"
          className="flex-1 rounded-xl bg-black/30 border border-white/10 focus:border-purple/60 outline-none px-4 py-3 text-sm"
        />
        <button
          onClick={send}
          disabled={loading}
          className="bg-purple hover:bg-purple/80 disabled:opacity-50 text-teal-deep font-extrabold px-4 rounded-xl transition"
        >
          <Send size={16} />
        </button>
      </div>
    </div>
  );
}
