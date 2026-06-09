import { useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

export default function PageHeader({ kicker, title, sub }: { kicker: string; title: string; sub?: string }) {
  const nav = useNavigate();
  return (
    <div className="mb-6">
      <button
        onClick={() => nav("/")}
        className="flex items-center gap-1.5 text-[0.7rem] text-white/45 hover:text-white mb-3 transition"
      >
        <ArrowLeft size={13} /> Deck Hub
      </button>
      <div className="text-[0.62rem] font-extrabold tracking-[0.14em] uppercase text-orange">{kicker}</div>
      <h1 className="text-2xl font-extrabold mt-1">{title}</h1>
      {sub && <p className="text-white/55 text-sm mt-1">{sub}</p>}
    </div>
  );
}
