# COGS Negotiation Agent

A Databricks-native, agentic application that helps **Kroger category negotiators**
prepare for and run supplier COGS (cost-of-goods-sold) negotiations across the
beverage category (PepsiCo, Coca-Cola, Keurig Dr Pepper).

> **Live app:** https://cogs-negotiation-agent-7405614449041750.10.azure.databricksapps.com

---

## What it does

| Feature | What it gives you |
|---|---|
| 🧭 **Negotiator (AI)** | Ask anything in plain English — a tool-calling agent picks & chains tools (Genie · RAG · deck), with a visible **tool trace** |
| 📊 **Supplier Scorecard** | Live Genie NL→SQL table + "Ask Genie" + an embedded **AI/BI dashboard** |
| ✍️ **Negotiation Brief** | Board-ready talking points **grounded in the supplier's contract** (RAG) |
| 📑 **Fact-Pack Deck** | A **fixed 15-slide / 5-act** negotiation deck, every number grounded in a table/clause — scroll or **▶ Present** (16:9 slides) |
| ⚔️ **Rehearsal Room** | Role-play practice against the supplier's account manager (isolated persona) |

## Built on (all real Databricks primitives)

- **Unity Catalog** — Delta tables + a certified **Metric View** (`kroger_demo.cogs`)
- **Genie** — natural-language → SQL over the metric view
- **Vector Search** — RAG over contract MSAs stored in a UC **Volume**
- **Mosaic AI Model Serving** — the agent registered + served from UC
- **Agent Evaluation** — LLM judges (correctness, safety, relevance, custom guidelines) offline + scheduled on live traffic; inference tables on
- **Lakebase** — Postgres OLTP persistence for saved work
- **AI/BI (Lakeview)** — an embedded dashboard with global filters
- **Databricks App** — React + FastAPI front end
- ★ **Pluggable LLM layer** — one LangChain interface, switch **Mosaic AI Gateway ↔ LiteLLM** with a single env var

## How it works

📖 **See [`ARCHITECTURE.md`](./ARCHITECTURE.md)** for the full end-to-end explanation:
the 3-layer architecture, every component, request-flow traces, deployment steps,
how to switch the LLM provider, and a complete resource inventory.

🖼️ **See [`cogs-agent-flow.html`](./cogs-agent-flow.html)** for the visual
"How It Works" diagram (open in a browser; has an Export-PDF button).

## Quick start (local dev)

```bash
export DATABRICKS_PROFILE=cogs-demo
uv run uvicorn app:app --reload --port 8000      # backend  → :8000
cd frontend && npm install && npm run dev          # frontend → :5173 (proxies /api)
```

## Deploy to a new workspace

Everything workspace-side (Delta data, Genie space, Vector Search, dashboard)
is recreated by one command. Knobs default to the cogs-demo values, so set env
(or copy `.env.example` → `.env`) only for a different target:

```bash
export DATABRICKS_PROFILE=<your-cli-profile>
export COGS_CATALOG=<catalog>            # default kroger_demo
export COGS_SCHEMA=<schema>              # default cogs
export VS_ENDPOINT=<vector-search-name>  # bootstrap CREATES it if missing
# WAREHOUSE_ID optional — auto-picks a serverless warehouse if unset

python bootstrap.py            # data_foundation → market_data → genie → knowledge → dashboard
```

`bootstrap.py` runs the build steps in dependency order and writes the created
IDs (Genie space, dashboard, warehouse, contract index) to `deploy_state.json`.
It then prints that state, the exact **app.yaml env block to paste**
(`GENIE_SPACE_ID`, `CONTRACT_INDEX`, `DASHBOARD_ID`, `COGS_CATALOG`,
`COGS_SCHEMA`, `WAREHOUSE_ID`), and the follow-up commands.

Then register/serve the agent and deploy the app:

```bash
python deploy_agent.py          # or: python bootstrap.py --deploy-agent (does both)
cd frontend && npm install && npm run build && cd ..
databricks sync . /Users/<you>/cogs-negotiation-agent --exclude node_modules --exclude .venv
databricks apps deploy cogs-negotiation-agent \
  --source-code-path /Workspace/Users/<you>/cogs-negotiation-agent
```

Finally attach app resources (UI or CLI): the **LLM serving endpoint**
(`CAN_QUERY`) and the **Lakebase database** (`CAN_CONNECT_AND_CREATE`).
`deploy_state.json` is workspace-specific runtime output and is git-ignored.

## Switch the LLM provider

In `app.yaml` set `LLM_PROVIDER: mosaic` (default, governed) or `litellm`
(point `LITELLM_BASE_URL` at your proxy) and redeploy. No agent code changes —
see [`ARCHITECTURE.md` §7](./ARCHITECTURE.md#7-switching-the-llm-provider-mosaic--litellm).

## Repo map

```
app.py · app.yaml            FastAPI entry + Databricks App config
server/llm.py                ★ pluggable LLM factory (Mosaic ↔ LiteLLM)
server/{agents,supervisor,genie,knowledge,state}.py   agent logic + integrations
server/routes/               FastAPI routers
frontend/                    React + Vite + TS + Tailwind UI
agent_model.py · deploy_agent.py     agent-as-model (MLflow + Mosaic AI Serving)
data_foundation.py · build_genie.py · build_knowledge.py · build_dashboard.py
                             one-time builders for the UC data + AI assets
ARCHITECTURE.md              full end-to-end documentation
cogs-agent-flow.html         visual architecture diagram
```
