// Thin API client. All calls hit the FastAPI backend under /api.

export interface Supplier {
  supplier: string;
  key: string;
  category: string;
  annual_spend: number;
  cogs_per_unit: number;
  unit_volume: number;
  landed_cost_index: number;
  yoy_cogs_change_pct: number;
  yoy_volume_change_pct: number;
  trade_funds_pct: number;
  fill_rate_pct: number;
  otif_pct: number;
  contract_expiry: string;
  rebate_tier: string;
  open_negotiation: boolean;
}

export interface HubCard {
  key: string;
  supplier: string;
  category: string;
  annual_spend: number;
  yoy_cogs_change_pct: number;
  contract_expiry: string;
  open_negotiation: boolean;
}

export interface Kpi { label: string; value: string; delta: string; tone: string; }
export interface DeckSection { heading: string; narrative: string; callout: string; }
export interface Deck {
  title: string; subtitle: string; hypothesis: string;
  kpis: Kpi[]; sections: DeckSection[]; asks: string[];
}

export interface SupervisorResult {
  route: "scorecard" | "brief" | "deck" | "rehearse" | "chat";
  supplier_key?: string | null;
  supplier?: string;
  answer?: string | null;
  sql?: string | null;
  columns?: string[];
  rows?: string[][];
  deck?: Deck;
}

export interface LlmStatus {
  provider: string; model: string; governed?: boolean;
  gateway_url?: string; litellm_base_url?: string; routes_via_mosaic?: boolean;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(`/api${path}`);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export interface GenieResult {
  text: string | null;
  sql: string | null;
  columns: string[];
  rows: string[][];
  conversation_id?: string;
  query_error?: string;
}

export const api = {
  health: () => get<{ status: string; llm: LlmStatus; state_backend: string }>("/health"),
  genieStatus: () => get<{ configured: boolean; space_id: string }>("/genie/status"),
  genieScorecard: () => get<GenieResult>("/genie/scorecard"),
  dashboard: () => get<{ dashboard_id: string; embed_url: string; full_url: string }>("/dashboard"),
  genieAsk: (question: string, conversation_id?: string) =>
    post<GenieResult>("/genie/ask", { question, conversation_id }),
  supervisorAsk: (message: string, history: { role: string; content: string }[]) =>
    post<SupervisorResult>("/supervisor/ask", { message, history }),
  feedback: (p: { artifact_id?: string; kind: string; rating: "up" | "down"; comment?: string; supplier_key?: string }) =>
    post<{ id: string; status: string }>("/feedback", p),
  hub: () => get<{ cards: HubCard[] }>("/hub"),
  overview: () => get<any>("/overview"),
  scorecard: (supplier?: string) =>
    get<{ suppliers: Supplier[] }>(`/scorecard${supplier ? `?supplier=${supplier}` : ""}`),
  brief: (supplier_key: string, objective: string) =>
    post<{ id: string; supplier: string; content: string; sources: { section: string; supplier: string }[] }>(
      "/brief", { supplier_key, objective }),
  deck: (supplier_key: string, objective: string) =>
    post<{ id: string; supplier: string; deck: Deck }>("/deck", { supplier_key, objective }),
  rehearse: (supplier_key: string, message: string, history: { role: string; content: string }[]) =>
    post<{ supplier: string; reply: string }>("/rehearse", { supplier_key, message, history }),
};

export const fmtMoney = (n: number): string => {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
};
