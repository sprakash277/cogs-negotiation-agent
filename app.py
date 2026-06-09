"""FastAPI entry point for the COGS Negotiation Agent Databricks App.

Serves the JSON API under /api and the built React SPA for everything else.
"""

from __future__ import annotations

import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from server import state
from server.routes import agentic, catalog, genie_routes, supervisor_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Opens the Lakebase pool + ensures schema when configured; no-op otherwise.
    state.init()
    yield
    state.shutdown()


app = FastAPI(title="COGS Negotiation Agent", lifespan=lifespan)

app.include_router(catalog.router, prefix="/api")
app.include_router(agentic.router, prefix="/api")
app.include_router(genie_routes.router, prefix="/api")
app.include_router(supervisor_routes.router, prefix="/api")

# Serve the built React frontend (frontend/dist) for all non-API routes.
_frontend = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.isdir(_frontend):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend, "assets")), name="assets")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        # Let the SPA router handle client-side paths.
        return FileResponse(os.path.join(_frontend, "index.html"))
