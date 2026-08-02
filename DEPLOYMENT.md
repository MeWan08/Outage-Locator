# Deployment

## Local (Docker)

```bash
docker compose up --build
```

Open http://localhost:8000. First boot seeds a synthetic network automatically
(a few seconds, logged to stdout as `[startup] seeded synthetic network: {...}`).
Data persists in a named volume (`outage-data`) across restarts; delete the volume
(`docker compose down -v`) to force a fresh reseed.

## Local (no Docker)

```bash
# backend
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend, separate terminal
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api to :8000
```

For a single combined server matching the Docker image exactly:

```bash
cd frontend && npm install && npm run build
cp -r dist ../backend/static
cd ../backend && uvicorn app.main:app
```

## Deploying to a public URL

This is a single container exposing port 8000 with no external dependencies (no
managed database required, SQLite lives on a volume) — it fits any platform that
runs a Dockerfile and gives you one persistent disk: Render, Railway, Fly.io, and
similar free/hobby tiers all work with no changes. General steps:

1. Push this repo to your own GitHub.
2. Point the platform at the repo; it should detect the `Dockerfile` automatically.
3. Attach a small persistent volume mounted at `/app/data` if the platform supports
   one (Render: "Disks"; Fly: `fly volumes create`; Railway: volumes). Without one,
   the network reseeds on every restart — not broken, just not persistent.
4. Optional: set `ANTHROPIC_API_KEY` as an environment variable to enable the AI
   dispatch-note feature. Leave it unset and the system works fully without it.
5. Expose port `8000`.

I was not able to actually perform this step or record a demo video from the
environment I built this in (no outbound access to hosting platforms, no video
capture) — the steps above are accurate for the image as built and tested locally,
but you'll need to carry out the actual deploy and recording yourself.

## Environment variables

All optional; sane defaults ship in `backend/app/config.py`. The ones worth knowing:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:////app/data/outages.db` | swap for a Postgres URL if scaling out (see ARCHITECTURE.md) |
| `SEED_POLE_COUNT` | `3600` | size of the synthetic network generated on first boot |
| `ANTHROPIC_API_KEY` | unset | enables the AI dispatch-note feature |
| `DEBOUNCE_SECONDS` | `30` | how long a candidate must persist before becoming a ticket |
| `RESTORATION_STABILITY_SECONDS` | `45` | how long poles must stay live before auto-verifying |
| `HEARTBEAT_INTERVAL_SECONDS` | `900` | simulated device heartbeat cadence (15 min, matches the brief) |
| `SCHEDULED_OUTAGE_GRACE_SECONDS` | `2400` | buffer either side of a declared maintenance window |

Full list, with the reasoning for each default, is in `backend/app/config.py`.

## Troubleshooting

**Container starts but `/` 404s / shows a blank page.** The frontend didn't build
into the image — check the `frontend-build` stage of the Docker build log for npm
errors. `docker build --progress=plain .` shows the full output.

**`database is locked` under load.** SQLite's single-writer model; the batched
writer in `ingestion.py` exists specifically to avoid this under normal load (see
ARCHITECTURE.md's measured throughput). If you're hitting it, you're likely calling
`/api/telemetry` (single) in a tight concurrent loop rather than `/telemetry/batch`
— batch calls coalesce into far fewer transactions.

**No incidents ever appear.** Check the simulator actually reached a device-equipped
pole (`GET /api/simulator/status` shows currently-faulted pole IDs) and that
`DEBOUNCE_SECONDS` plus one detection tick (`DETECTION_LOOP_INTERVAL_SECONDS`,
default 5s) has actually elapsed — a fault needs ~35s by default before a ticket
appears, which is intentional (see DECISIONS.md) but easy to mistake for "it's not
working" if you check immediately.

**Confidence always low / topology always "inferred."** Expected for ~60% of
transformers by design — pick a DT for the simulator's `dt_id` field and check
`GET /api/topology/{dt_id}` to see its `topology_source` before assuming something's
wrong.

**Wanting to reset without a full `docker compose down -v`.** There's no admin
endpoint for this by design (keeps the API surface small); delete the SQLite file in
the mounted volume and restart the container.
