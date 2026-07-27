from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIST
from .db import connect, migrate
from .routers import feed, instructions, pipeline, sources
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

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
