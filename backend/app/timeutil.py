"""
SQLite does not preserve tzinfo across a round-trip even through a
SQLAlchemy DateTime(timezone=True) column — values read back from the DB
are naive. Rather than fight that on every read, the whole app standardizes
on naive-but-implicitly-UTC datetimes for anything that touches the
database or gets compared against something that did. Pure functions in
localization.py/topology.py don't care either way (they only ever diff two
datetimes the caller gave them) — this matters only at the boundaries:
ingestion (incoming `ts` from a device payload) and the detection loop
(`now`).
"""
import datetime as dt


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def as_naive_utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(dt.timezone.utc).replace(tzinfo=None)
    return value
