# KSPDB Outage Locator

A fault-localization and ticketing system for a fictional electricity distribution
board's LT (low-tension) network: it takes noisy pole-top telemetry, figures out
*where* the fault actually is on a mostly-unmapped radial network, opens a ticket
with a defensible confidence score, and closes the loop by verifying restoration
from telemetry rather than trusting a human's word for it.

Built in response to the case study in `00-candidate-brief.md` / `01-04-*.md`. See:

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — how the localization algorithm works, the
  data model, the API, and known limitations. Start here if you want to understand
  the reasoning, not just run the thing.
- **[DECISIONS.md](DECISIONS.md)** — the specific judgment calls and why.
- **[AI-WORKFLOW.md](AI-WORKFLOW.md)** — the one AI-shaped feature, and how AI was
  (and wasn't) used to build this.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — running it, deploying it, troubleshooting.

## Quick start

```bash
git clone <this-repo>
cd outage-locator
docker compose up --build
```

Open **http://localhost:8000**. On first boot it seeds a synthetic ~3,600-pole
network automatically (a few seconds) — no manual migration or seed step.

No API key is required for anything to work. Setting `ANTHROPIC_API_KEY` (in a
`.env` file, see `.env.example`) turns on the AI dispatch-note feature; without it,
incidents get a deterministic templated summary instead — every other part of the
system, including localization itself, has no AI dependency at all.

## Driving it

The **Simulator** tab in the console injects faults (span / transformer / feeder /
device-only), repairs them, runs a multi-fault "storm," and declares scheduled
outages — this *is* the evaluation harness, not a demo toy. Equivalently, from a
terminal:

```bash
curl -X POST localhost:8000/api/simulator/fault \
  -H 'content-type: application/json' \
  -d '{"kind": "span", "dt_id": "D-0012"}'

curl localhost:8000/api/incidents
```

A new ticket should appear within `DEBOUNCE_SECONDS` (30s default) + the next
detection tick — comfortably under the 120s target.

## Repository layout

```
backend/app/
  topology.py        known-topology passthrough + geometric MST inference
  localization.py     the core algorithm — pure, unit-tested, no DB
  ingestion.py         telemetry dedup/ordering + async batched writer
  scheduled_outages.py load-shedding-feed matching (exact scope, with grace)
  tickets.py            lifecycle state machine, telemetry-only verification
  background.py         orchestration: debounce, supersession, restoration checks
  simulator.py           fault injection + continuous fleet-heartbeat simulation
  ai_briefing.py          the one AI feature, with a deterministic fallback
  seed.py                  synthetic network generator
  routers/                 FastAPI endpoints
backend/tests/           pytest — mostly localization.py and topology.py
frontend/                React + Leaflet operator console
scripts/loadtest.py      throughput measurement (see ARCHITECTURE.md for results)
```

## Tests

```bash
cd backend && python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

21 tests, all against the localization/topology modules — the part of this system
where being wrong is expensive. See ARCHITECTURE.md for what else was verified by
hand (end-to-end lifecycle, scheduled-outage suppression, escalation/supersession)
and wasn't converted into automated fixtures given the time box.
