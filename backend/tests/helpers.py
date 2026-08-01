import datetime as dt

from app.config import Settings
from app.localization import DtMeta, PoleSnapshot
from app.topology import PoleRecord, resolve_dt_topology

NOW = dt.datetime(2026, 7, 31, 10, 0, 0, tzinfo=dt.timezone.utc)


def cfg():
    """Fresh default-valued settings object per test, independent of any
    environment variables set on the machine running the suite."""
    return Settings()


def make_dt_meta(dt_id, feeder_id, dt_lat, dt_lon, households, pole_records: list[PoleRecord]) -> DtMeta:
    topo = resolve_dt_topology(dt_id, dt_lat, dt_lon, pole_records)
    return DtMeta(dt_id=dt_id, feeder_id=feeder_id, lat=dt_lat, lon=dt_lon,
                  households_served=households, topology=topo)


def snap(pole_id, dt_id, feeder_id, lat, lon, raw_status, *, pincode=None,
         has_device=True, energized=None, last_received_at=None) -> PoleSnapshot:
    return PoleSnapshot(
        pole_id=pole_id, dt_id=dt_id, feeder_id=feeder_id, lat=lat, lon=lon,
        pincode=pincode, has_device=has_device, energized=energized,
        last_received_at=last_received_at, raw_status=raw_status,
    )
