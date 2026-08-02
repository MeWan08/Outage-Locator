import asyncio
import contextlib
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import background, ingestion, seed, simulator
from app.config import settings
from app.db import init_db, session_scope
from app.routers import incidents, meta, telemetry
from app.routers import simulator as simulator_router

_background_tasks: list[asyncio.Task] = []


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    with session_scope() as db:
        if settings.SEED_ON_EMPTY and seed.is_db_empty(db):
            stats = seed.run_seed(settings.SEED_POLE_COUNT, settings.SEED_RANDOM_SEED)
            print(f"[startup] seeded synthetic network: {stats}")

    with session_scope() as db:
        background.build_topology_cache(db)
    ingestion.refresh_known_pole_ids()
    print(f"[startup] topology cache built for {len(background.all_dt_ids())} transformers")

    _background_tasks.append(asyncio.create_task(ingestion.batched_writer_loop()))
    _background_tasks.append(asyncio.create_task(background.run_forever()))
    _background_tasks.append(asyncio.create_task(simulator.fleet_heartbeat_loop()))

    yield

    for t in _background_tasks:
        t.cancel()


app = FastAPI(title="KSPDB Outage Locator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(telemetry.router)
app.include_router(incidents.router)
app.include_router(meta.router)
app.include_router(simulator_router.router)

_FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_FRONTEND_DIST):
    _assets_dir = os.path.join(_FRONTEND_DIST, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = os.path.join(_FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_FRONTEND_DIST, "index.html"))
