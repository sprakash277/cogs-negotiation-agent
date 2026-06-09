import { useState } from "react";
import { ThumbsUp, ThumbsDown, Check } from "lucide-react";
import { api } from "../api";

/**
 * Lightweight 👍/👎 + optional comment, persisted to Lakebase via /api/feedback.
 * Feeds the human side of the Quality Loop (promote_feedback.py turns 👎 into eval cases).
 */
export default function Feedback({
  artifactId,
  kind,
  supplierKey,
}: {
  artifactId?: string;
  kind: string;
  supplierKey?: string;
}) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);

  async function send(r: "up" | "down") {
    setRating(r);
    // 👍 sends immediately; 👎 waits for an optional comment via the Send button.
    if (r === "up") {
      await submit(r, "");
    }
  }

  async function submit(r: "up" | "down", c: string) {
    try {
      await api.feedback({ artifact_id: artifactId, kind, rating: r, comment: c || undefined, supplier_key: supplierKey });
      setSent(true);
    } catch {
      /* non-blocking */
    }
  }

  if (sent) {
    return (
      <div className="flex items-center gap-1.5 text-[0.72rem] text-mint mt-3">
        <Check size={13} /> Thanks — feedback recorded.
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-[0.7rem] text-white/45">Was this useful?</span>
        <button
          onClick={() => send("up")}
          className={`p-1.5 rounded-md border transition ${rating === "up" ? "border-mint/50 bg-mint/15 text-mint" : "border-white/10 text-white/50 hover:text-mint hover:border-mint/40"}`}
          title="Helpful"
        >
          <ThumbsUp size={13} />
        </button>
        <button
          onClick={() => send("down")}
          className={`p-1.5 rounded-md border transition ${rating === "down" ? "border-rose/50 bg-rose/15 text-rose" : "border-white/10 text-white/50 hover:text-rose hover:border-rose/40"}`}
          title="Not helpful"
        >
          <ThumbsDown size={13} />
        </button>
      </div>
      {rating === "down" && (
        <div className="flex gap-2">
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit("down", comment)}
            placeholder="What was wrong? (e.g. OTIF number is stale)"
            className="flex-1 rounded-lg bg-black/30 border border-white/10 focus:border-rose/50 outline-none px-3 py-2 text-xs"
          />
          <button
            onClick={() => submit("down", comment)}
            className="bg-rose/80 hover:bg-rose text-teal-deep font-bold text-xs px-3 rounded-lg"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
