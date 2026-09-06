"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import approvals, chat, gdpr, health

DESCRIPTION = """
Multi-tenant, EU-compliant agentic customer support and sales.

**How it works.** The agent reads a customer message, calls real systems to
establish the facts, and drafts a reply. Deterministic code — not the model —
then decides whether that reply goes out on its own or waits for a human.

**What makes it different.** Personal data never leaves the EEA: it is replaced
with opaque tokens before any model call, and the mapping stays in-region.
Nothing that moves money is ever autonomous. Every decision is written to an
append-only log the database itself refuses to alter.
"""


def create_app() -> FastAPI:
    app = FastAPI(
        title="Universal Sales Agent",
        description=DESCRIPTION,
        version=__version__,
        openapi_tags=[
            {"name": "health", "description": "Liveness and data-residency posture."},
            {"name": "chat", "description": "Customer conversation turns and the active policy."},
            {"name": "approvals", "description": "Human oversight queue (EU AI Act Art. 14)."},
            {"name": "gdpr", "description": "Subject access and erasure (GDPR Art. 15/17)."},
        ],
    )
    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(approvals.router)
    app.include_router(gdpr.router)

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    def operator_console() -> FileResponse:
        """The approval queue. Article 14 oversight has to be somewhere a human
        can actually reach."""
        return FileResponse(static_dir / "index.html")

    return app


app = create_app()
