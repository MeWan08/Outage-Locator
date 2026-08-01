"""Small geo helpers. No external geocoding dependency — see ARCHITECTURE.md
§5 for why: pincode comes from the registry for ~97% of poles, and the
remaining ~3% are filled by nearest-known-neighbour within the same
transformer, which needs nothing but coordinates we already have."""
import math


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres. Fine at this scale (poles are metres
    to low-km apart) — no need for a geodesic library."""
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float):
    return ((lat1 + lat2) / 2.0, (lon1 + lon2) / 2.0)


def centroid(points):
    pts = list(points)
    if not pts:
        return (None, None)
    lat = sum(p[0] for p in pts) / len(pts)
    lon = sum(p[1] for p in pts) / len(pts)
    return (lat, lon)


def nearest_pincode(target_lat, target_lon, candidates):
    """candidates: iterable of (lat, lon, pincode) with pincode not None.
    Returns the pincode of the geographically closest candidate, or None."""
    best_pincode, best_dist = None, float("inf")
    for lat, lon, pincode in candidates:
        if pincode is None:
            continue
        d = haversine_m(target_lat, target_lon, lat, lon)
        if d < best_dist:
            best_dist, best_pincode = d, pincode
    return best_pincode
