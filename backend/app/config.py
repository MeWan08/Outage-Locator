"""
All tunables live here and are overridable via environment variables.
Nothing in this file should require a code change to retune the system —
that's the point of pulling it out of the algorithm modules.
"""
import os


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # --- Storage ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:////app/data/outages.db")

    # --- Seeding ---
    SEED_ON_EMPTY: bool = _bool("SEED_ON_EMPTY", True)
    SEED_POLE_COUNT: int = _int("SEED_POLE_COUNT", 3600)
    SEED_RANDOM_SEED: int = _int("SEED_RANDOM_SEED", 42)

    # --- Telemetry / device behaviour (mirrors 02-data-and-systems.md) ---
    HEARTBEAT_INTERVAL_SECONDS: int = _int("HEARTBEAT_INTERVAL_SECONDS", 900)  # 15 min
    HEARTBEAT_JITTER_SECONDS: int = _int("HEARTBEAT_JITTER_SECONDS", 45)
    # A pole is "silent" once it has missed this many heartbeat windows.
    MISSED_HEARTBEATS_FOR_SILENCE: int = _int("MISSED_HEARTBEATS_FOR_SILENCE", 2)
    CLOCK_SKEW_TOLERANCE_SECONDS: int = _int("CLOCK_SKEW_TOLERANCE_SECONDS", 90)

    # --- Detection / debounce ---
    # Wait this long after the first dark signal in an area before opening a
    # ticket, so a single storm doesn't fire 40 half-formed incidents while
    # telemetry is still arriving.
    DEBOUNCE_SECONDS: int = _int("DEBOUNCE_SECONDS", 30)
    # Background loop cadence.
    DETECTION_LOOP_INTERVAL_SECONDS: float = _float("DETECTION_LOOP_INTERVAL_SECONDS", 5.0)
    # How long poles must stay live before we auto-verify a restoration.
    RESTORATION_STABILITY_SECONDS: int = _int("RESTORATION_STABILITY_SECONDS", 45)

    # --- Scheduled outage matching ---
    SCHEDULED_OUTAGE_GRACE_SECONDS: int = _int("SCHEDULED_OUTAGE_GRACE_SECONDS", 40 * 60)

    # --- Confidence scoring weights (see ARCHITECTURE.md for rationale) ---
    CONF_BASE: float = _float("CONF_BASE", 0.90)
    CONF_PENALTY_INFERRED_TOPOLOGY: float = _float("CONF_PENALTY_INFERRED_TOPOLOGY", 0.30)
    CONF_PENALTY_COVERAGE_GAP: float = _float("CONF_PENALTY_COVERAGE_GAP", 0.20)
    CONF_PENALTY_SILENCE_ONLY: float = _float("CONF_PENALTY_SILENCE_ONLY", 0.12)
    CONF_PENALTY_STALE_REFERENCE: float = _float("CONF_PENALTY_STALE_REFERENCE", 0.10)
    CONF_PENALTY_AMBIGUOUS_TOPOLOGY: float = _float("CONF_PENALTY_AMBIGUOUS_TOPOLOGY", 0.08)
    CONF_BONUS_CORROBORATION: float = _float("CONF_BONUS_CORROBORATION", 0.05)
    CONF_MIN: float = _float("CONF_MIN", 0.05)
    CONF_MAX: float = _float("CONF_MAX", 0.99)

    # --- Ingestion write-batching ---
    INGEST_QUEUE_MAXSIZE: int = _int("INGEST_QUEUE_MAXSIZE", 20000)
    INGEST_BATCH_MAX_SIZE: int = _int("INGEST_BATCH_MAX_SIZE", 300)
    INGEST_BATCH_MAX_WAIT_SECONDS: float = _float("INGEST_BATCH_MAX_WAIT_SECONDS", 0.25)

    # --- AI briefing feature ---
    ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
    AI_BRIEFING_MODEL: str = os.environ.get("AI_BRIEFING_MODEL", "claude-sonnet-5")
    AI_BRIEFING_ENABLED: bool = _bool("AI_BRIEFING_ENABLED", True)
    AI_BRIEFING_TIMEOUT_SECONDS: float = _float("AI_BRIEFING_TIMEOUT_SECONDS", 8.0)

    # --- Misc ---
    CORS_ORIGINS: list = os.environ.get("CORS_ORIGINS", "*").split(",")


settings = Settings()
