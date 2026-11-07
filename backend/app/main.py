"""Recommender Feed API server: FastAPI app serving /api/* and the built frontend.

A personal reading feed ranked by LLM agents. This process is the web UI + API; the
fetch/triage/rank pipeline is a separate CLI (`python -m app.pipeline`), started by
launchd on a schedule or by the UI's Refresh button.

Config and data: FEEDAPP_DATA_DIR, else the sibling ../data of the checkout (feed.db,
.env with ANTHROPIC_API_KEY, backups/). Logs: ~/Library/Logs/recommender-feed-server.log
under launchd; the pipeline logs to ~/Library/Logs/recommender-feed.log. See README.md.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .db import connect, migrate
from .routers import conversation, feed, instructions, pipeline, sources
from .seed import seed_defaults
from .services.profile import ensure_profile


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate()
    conn = connect()
    try:
        seed_defaults(conn)
        ensure_profile(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Recommender Feed", lifespan=lifespan)


@app.middleware("http")
async def no_cache_html(request, call_next):
    """Never let the browser cache index.html — otherwise a stale shell keeps
    loading old JS bundles after rebuilds. Hashed assets stay cacheable."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("text/html"):
        response.headers["Cache-Control"] = "no-cache"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feed.router, prefix="/api")
app.include_router(sources.router, prefix="/api")
app.include_router(instructions.router, prefix="/api")
app.include_router(pipeline.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
