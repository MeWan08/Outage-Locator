# Deployment & Configuration

This guide details how to deploy LumenGrid locally and in the cloud, and outlines the key environment variables that control system behavior.

## Local (Docker Compose)

The standard and most reliable way to run the application is via Docker Compose, which brings up both the FastAPI backend and the compiled React frontend in a single container.

```bash
# Start the system in the background
docker compose up --build -d
```

Open `http://localhost:8000`. On first boot, the system automatically seeds a synthetic network topology (this takes a few seconds). Data persists in a named Docker volume (`outage-data`) across restarts. To force a fresh reseed and delete all data, tear down the volume: `docker compose down -v`.

## Cloud Deployment (AWS EC2)

Because LumenGrid is a self-contained monolithic container with no external database dependencies (using SQLite on a persistent volume), it is extremely cheap and easy to host on the AWS Free Tier.

1. **Launch an EC2 Instance:** Launch a `t2.micro` or `t3.micro` instance running Ubuntu.
2. **Open Ports:** In the EC2 Security Group, allow inbound TCP traffic on port `8000` from anywhere (`0.0.0.0/0`).
3. **Install Docker:** SSH into the instance and install Docker (`sudo apt update && sudo apt install docker.io docker-compose-v2 git -y`).
4. **Clone and Configure:**
   ```bash
   git clone https://github.com/MeWan08/Outage-Locator.git
   cd Outage-Locator
   
   # IMPORTANT: The .env file is gitignored for security. 
   # You MUST recreate it on the server to enable AI features.
   echo "GROQ_API_KEY=your_api_key_here" > .env
   ```
5. **Run:** `sudo docker compose up --build -d`

## Environment Variables

All configuration is managed via environment variables. Sane defaults are provided in `backend/app/config.py`, but many of these are explicitly overridden in `docker-compose.yml` for optimal performance.

| Variable | Current Configured Value | Purpose |
|---|---|---|
| `GROQ_API_KEY` | *(Set in .env)* | Enables the AI dispatch-note feature using Llama 3.3. If unset, falls back to a deterministic string template. |
| `DATABASE_URL` | `sqlite:////app/data/outages.db` | Swap for a PostgreSQL URL if scaling out horizontally (see ARCHITECTURE.md). |
| `SEED_POLE_COUNT` | `3600` | Size of the synthetic network generated on first boot. |
| `DEBOUNCE_SECONDS` | `30` | **(Set in docker-compose)** How long a candidate fault must persist across detection loops before becoming an actionable ticket. 30s allows staggered telemetry from a severe storm to arrive and consolidate into a single ticket. |
| `RESTORATION_STABILITY_SECONDS` | `30` | **(Set in docker-compose)** How long repaired poles must stay continuously live before the system auto-verifies and closes the incident ticket. |
| `HEARTBEAT_INTERVAL_SECONDS` | `15` | **(Set in docker-compose)** Simulated device heartbeat cadence. A fast 15s interval keeps the demo UI responsive. |
| `MISSED_HEARTBEATS_FOR_SILENCE`| `1` | **(Set in docker-compose)** How many heartbeats a sensor can miss before being marked as offline/dark. |
| `SCHEDULED_OUTAGE_GRACE_SECONDS`| `2400` | Buffer (in seconds) on either side of a declared maintenance window where faults are suppressed. |

## Troubleshooting

**Container starts but `/` 404s or shows a blank page.** 
The frontend didn't build into the image successfully. Check the `frontend-build` stage of the Docker build log for NPM errors by running `docker compose build --progress=plain`.

**`database is locked` under load.** 
This is SQLite's single-writer limitation. The batched writer in `ingestion.py` exists specifically to avoid this. If you encounter this, you are likely calling `/api/telemetry` (single insert) in a tight loop rather than using the optimized `/telemetry/batch` endpoint.

**No incidents ever appear after injecting a fault.** 
Check if the simulator actually reached a device-equipped pole (`GET /api/simulator/status`). Secondly, remember that `DEBOUNCE_SECONDS` is set to 30 seconds. A fault needs at least 30 seconds to solidify into a ticket. This is intentional to prevent ticket flapping. Wait 30 seconds before assuming it failed!

**Confidence is always low / topology says "inferred".** 
This is expected by design for ~60% of transformers that lack surveyed wiring data. The system uses a Geometric MST to guess the wiring, which mathematically incurs a confidence penalty.

**I want to factory reset everything.** 
Since data is stored on a persistent Docker volume, simply running `docker compose down` won't wipe the database. You must run `docker compose down -v` to destroy the volume, then restart.
