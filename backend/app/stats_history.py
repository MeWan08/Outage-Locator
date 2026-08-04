"""
In-memory ring buffer that records one snapshot per detection tick.
Used by GET /api/stats/history to power the front-end trend mini-charts.
No database change needed — the data only needs to live while the process
is alive (same contract as the pending-candidates debounce dict).
"""
from collections import deque
from app.timeutil import utcnow

_MAX = 120  # keep last 120 snapshots (~10 min at 5s/tick)
_history: deque = deque(maxlen=_MAX)


def record(open_incidents: int, poles_dark: int, total_poles: int):
    _history.append({
        "ts": utcnow().isoformat(),
        "open_incidents": open_incidents,
        "poles_dark": poles_dark,
        "total_poles": total_poles,
    })


def get_history(limit: int = 60) -> list:
    return list(_history)[-limit:]
