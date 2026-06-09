import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { LayoutGrid, BarChart3, ShieldCheck, Zap, Compass } from "lucide-react";
import { api, LlmStatus } from "../api";

const items = [
  { to: "/negotiator", label: "Negotiator (AI)", icon: Compass, exact: true },
  { to: "/", label: "Deck Hub", icon: LayoutGrid, exact: true },
  { to: "/scorecard", label: "Supplier Scorecard", icon: BarChart3 },
];

export default function Sidebar() {
  const [llm, setLlm] = useState<LlmStatus | null>(null);
  const [stateBackend, setStateBackend] = useState<string>("");
  const loc = useLocation();

  useEffect(() => {
    api.health().then((h) => { setLlm(h.llm); setStateBackend(h.state_backend); }).catch(() => {});
  }, []);

  const governed = llm?.governed;

  return (
    <aside className="w-64 shrink-0 flex flex-col bg-gradient-to-b from-[#1a0f0a] via-[#14323d] to-[#080F14] border-r border-white/10">
      <div className="px-5 pt-6 pb-5">
        <div className="text-[0.62rem] font-extrabold tracking-[0.18em] text-white/45 uppercase">Kroger Sourcing</div>
        <div className="mt-1 text-lg font-extrabold leading-tight">
          COGS <span className="text-orange">Negotiator</span>
        </div>
        <div className="text-[0.7rem] text-white/50 mt-0.5">Console · Beverages</div>
      </div>

      <nav className="px-3 flex flex-col gap-1">
        {items.map(({ to, label, icon: Icon, exact }) => (
          <NavLink
            key={to}
            to={to}
            end={exact}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-semibold transition ${
                isActive
                  ? "bg-orange/15 text-white border border-orange/40"
                  : "text-white/60 hover:text-white hover:bg-white/5 border border-transparent"
              }`
            }
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-5 mt-5 text-[0.6rem] font-extrabold tracking-[0.12em] text-white/35 uppercase">
        Per-supplier actions
      </div>
      <div className="px-5 mt-2 text-[0.7rem] text-white/45 leading-relaxed">
        Open a supplier from the Deck Hub to generate a <span className="text-cyan">Fact-Pack</span>,
        a <span className="text-mint">Brief</span>, or run a <span className="text-purple">Rehearsal</span>.
      </div>

      <div className="mt-auto px-4 pb-5 pt-4">
        {/* LLM provider badge — the visible proof of the pluggable factory */}
        <div className="rounded-xl border border-white/10 bg-black/30 p-3">
          <div className="flex items-center gap-2 text-[0.62rem] font-extrabold tracking-wide uppercase text-white/45">
            <Zap size={12} /> LLM Routing
          </div>
          {llm ? (
            <>
              <div className="mt-1.5 flex items-center gap-2">
                <span className="text-sm font-extrabold text-white">
                  {llm.provider === "mosaic" ? "Mosaic AI Gateway" : llm.provider === "litellm" ? "LiteLLM" : llm.provider}
                </span>
              </div>
              <div className="text-[0.66rem] text-white/45 mt-0.5">{llm.model}</div>
              <div className={`mt-2 inline-flex items-center gap-1 text-[0.6rem] font-bold px-2 py-1 rounded-full ${
                governed ? "text-mint border border-mint/40 bg-mint/5" : "text-gold border border-gold/40 bg-gold/5"
              }`}>
                <ShieldCheck size={11} />
                {governed ? "Governed boundary" : "Direct · ungoverned"}
              </div>
            </>
          ) : (
            <div className="text-[0.66rem] text-white/40 mt-1">connecting…</div>
          )}
          <div className="text-[0.6rem] text-white/35 mt-2">state: {stateBackend || "…"}</div>
        </div>
      </div>
    </aside>
  );
}
