"""
Generates a fictional-but-plausible slice of a distribution network at
roughly the scale and proportions 02-data-and-systems.md describes (a
subdivision, not the whole 30-subdivision utility — 05-faq.md is explicit
that a few thousand poles across a few dozen DTs is the right scope for
this exercise). Runs once, automatically, on first boot against an empty
database (app/config.py SEED_ON_EMPTY) — no manual migration/seed step for
whoever runs `docker compose up`.

Physical layout: each DT grows a small tree of poles via a biased random
walk (a 'main line' with 1-4 branch points), not scattered points, so the
geometry is internally consistent — real electrical adjacency really does
correlate with physical proximity here, which is what makes the geometric
MST inference in app/topology.py a meaningful strategy rather than a random
guess. Whether a DT's seq_on_line/parent_pole_id are actually exposed in
the registry (vs withheld, forcing inference) is decided per-DT to hit the
~60% missing figure — coordinates are always present either way.
"""
import datetime as dt
import math
import random

from sqlalchemy import select

from app.db import session_scope
from app.models import Device, Feeder, Pole, PoleState, Substation, Transformer
from app.simulator import BUGGY_FIRMWARE_VERSIONS
from app import timeutil

# Rough Bengaluru-area bounding box — a fictional utility, but grounded in
# real-world coordinates so the map view looks like an actual city rather
# than an abstract grid.
CENTER_LAT, CENTER_LON = 12.972, 77.594

NORMAL_FIRMWARES = ["2.1.0", "2.1.0", "2.0.3", "2.2.0"]
PINCODE_BASE = 560001

FRACTION_DT_TOPOLOGY_KNOWN = 0.40
FRACTION_NO_DEVICE = 0.09
FRACTION_NO_PINCODE = 0.03
FRACTION_BUGGY_FIRMWARE = 0.08


def _rng_pole_count() -> int:
    # Lognormal-ish: median ~70, long tail up to the ~240 the brief mentions,
    # floor of 9 (a short spur off a small DT).
    val = int(random.lognormvariate(math.log(70), 0.6))
    return max(9, min(240, val))


def _walk_tree(n_poles: int, origin_lat: float, origin_lon: float, seed_bearing: float):
    """Yields (pole_index, lat, lon, parent_index) for a biased random walk
    with occasional branches. parent_index is -1 for the root (parents to
    the DT itself). Step size ~35-70m."""
    nodes = [(origin_lat, origin_lon)]
    parent_of = {0: -1}
    bearings = {0: seed_bearing}
    frontier = [0]
    branch_points_left = random.randint(1, 4) if n_poles > 15 else 0

    for i in range(1, n_poles):
        # Usually extend from the most recently added node (keeps mostly-
        # linear runs); occasionally branch from an earlier node.
        if branch_points_left > 0 and len(frontier) > 2 and random.random() < 0.15:
            src = random.choice(frontier[:-1])
            bearing = bearings[src] + random.choice([-1, 1]) * random.uniform(60, 140)
            branch_points_left -= 1
        else:
            src = frontier[-1]
            bearing = bearings[src] + random.uniform(-25, 25)

        step_m = random.uniform(35, 70)
        dlat = (step_m * math.cos(math.radians(bearing))) / 111_320
        dlon = (step_m * math.sin(math.radians(bearing))) / (111_320 * math.cos(math.radians(origin_lat)))
        lat, lon = nodes[src][0] + dlat, nodes[src][1] + dlon

        nodes.append((lat, lon))
        parent_of[i] = src
        bearings[i] = bearing
        frontier.append(i)

    return nodes, parent_of


def run_seed(target_pole_count: int, seed_value: int):
    random.seed(seed_value)
    now = timeutil.utcnow()

    with session_scope() as db:
        pole_counter = 0
        device_counter = 0
        dt_counter = 0
        feeder_counter = 0
        total_poles = 0
        n_substations = 3

        for ss_i in range(n_substations):
            ss_id = f"SS-{ss_i + 1}"
            ss_lat = CENTER_LAT + random.uniform(-0.06, 0.06)
            ss_lon = CENTER_LON + random.uniform(-0.06, 0.06)
            db.add(Substation(substation_id=ss_id, name=f"{ss_id} 110kV Receiving Station", lat=ss_lat, lon=ss_lon))
            db.flush()  # SQLite checks FKs immediately, not at commit — parents must exist first

            n_feeders = random.randint(3, 5)
            for _f in range(n_feeders):
                feeder_counter += 1
                feeder_id = f"F-{feeder_counter:02d}"
                db.add(Feeder(feeder_id=feeder_id, substation_id=ss_id, name=f"Feeder {feeder_id}"))
                db.flush()
                feeder_lat = ss_lat + random.uniform(-0.02, 0.02)
                feeder_lon = ss_lon + random.uniform(-0.02, 0.02)

                n_dts = random.randint(5, 9)
                for _d in range(n_dts):
                    if total_poles >= target_pole_count:
                        break
                    dt_counter += 1
                    dt_id = f"D-{dt_counter:04d}"
                    dt_lat = feeder_lat + random.uniform(-0.012, 0.012)
                    dt_lon = feeder_lon + random.uniform(-0.012, 0.012)
                    pincode = str(PINCODE_BASE + (dt_counter % 90))

                    n_poles = _rng_pole_count()
                    nodes, parent_of = _walk_tree(n_poles, dt_lat, dt_lon, random.uniform(0, 360))
                    topology_known = random.random() < FRACTION_DT_TOPOLOGY_KNOWN

                    households = int(n_poles * random.uniform(0.5, 0.9))
                    db.add(Transformer(
                        dt_id=dt_id, feeder_id=feeder_id, lat=dt_lat, lon=dt_lon,
                        capacity_kva=random.choice([25, 63, 100, 160, 250]),
                        households_served=households,
                        topology_source="known" if topology_known else "inferred",
                    ))
                    db.flush()  # Pole.dt_id references this row

                    dt_pole_ids = []
                    for idx in range(len(nodes)):
                        pole_counter += 1
                        dt_pole_ids.append(f"P-{pole_counter:06d}")

                    device_rows = []
                    for idx, (lat, lon) in enumerate(nodes):
                        pid = dt_pole_ids[idx]
                        parent_idx = parent_of[idx]
                        true_parent_id = dt_pole_ids[parent_idx] if parent_idx >= 0 else None
                        true_seq = idx + 1  # 1 = roots at the DT

                        has_device = random.random() >= FRACTION_NO_DEVICE
                        has_pincode = random.random() >= FRACTION_NO_PINCODE

                        device_id = None
                        fw = None
                        if has_device:
                            device_counter += 1
                            device_id = f"DEV-{device_counter:06d}"
                            fw = (random.choice(list(BUGGY_FIRMWARE_VERSIONS))
                                  if random.random() < FRACTION_BUGGY_FIRMWARE
                                  else random.choice(NORMAL_FIRMWARES))
                            device_rows.append((pid, device_id, fw))

                        db.add(Pole(
                            pole_id=pid, lat=lat, lon=lon, feeder_id=feeder_id, dt_id=dt_id,
                            seq_on_line=(true_seq if topology_known else None),
                            parent_pole_id=(true_parent_id if topology_known else None),
                            pole_type=random.choice(["LT", "LT", "LT", "service"]),
                            ward=f"Ward-{(dt_counter % 20) + 1}",
                            pincode=(pincode if has_pincode else None),
                            device_id=device_id,
                        ))

                    db.flush()  # PoleState.pole_id references the rows just added

                    for pid, device_id, fw in device_rows:
                        db.add(Device(
                            device_id=device_id, current_pole_id=pid, last_seq=0, boot_count=1,
                            last_fw=fw, first_seen_at=now, last_seen_at=now,
                        ))
                        db.add(PoleState(
                            pole_id=pid, device_id=device_id, energized=True, last_event="boot",
                            last_device_ts=now, last_received_at=now, last_seq=0,
                            battery_mv=random.randint(3600, 4100), rssi=random.randint(-95, -60), fw=fw,
                            became_live_at=now,
                        ))
                    db.flush()

                    total_poles += n_poles
                if total_poles >= target_pole_count:
                    break
            if total_poles >= target_pole_count:
                break

    return {"poles": total_poles, "transformers": dt_counter, "feeders": feeder_counter, "substations": n_substations}


def is_db_empty(db) -> bool:
    return db.execute(select(Pole.pole_id).limit(1)).first() is None
