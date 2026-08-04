import { useEffect, useState, useMemo, useCallback, useRef } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip, Polyline, useMap } from "react-leaflet";
import { api } from "../api.js";
import ConfidenceMeter from "./ConfidenceMeter.jsx";

/* ── Colors for light map ── */
const POLE_COLOR = {
  live: "#16a37a",
  dark: "#dc3545",
  unknown: "#8693a1",
  noDevice: "#bbc2cc",
};

const DT_COLOR = "#6d28d9"; // purple for transformers — distinct from poles

function poleColor(p) {
  if (!p.has_device) return POLE_COLOR.noDevice;
  if (p.energized === true) return POLE_COLOR.live;
  if (p.energized === false) return POLE_COLOR.dark;
  return POLE_COLOR.unknown;
}

function poleStatusText(p) {
  if (!p.has_device) return "no device";
  if (p.energized === false) return "dark";
  if (p.energized === true) return "live";
  return "unknown";
}

function timeAgoShort(iso) {
  if (!iso) return "never";
  const s = Math.max(0, (Date.now() - new Date(iso + (iso.endsWith("Z") ? "" : "Z")).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

/* ── Feeder color palette ── */
const FEEDER_COLORS = [
  "#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c",
  "#0891b2", "#ca8a04", "#db2777", "#4f46e5", "#059669",
];
function feederColor(feederId) {
  if (!feederId) return "#64748b";
  const num = parseInt(feederId.replace(/\D/g, ""), 10) || 0;
  return FEEDER_COLORS[num % FEEDER_COLORS.length];
}

const STATUS_COLORS = {
  detected: { bg: "bg-amber-50", text: "text-signal-copper", border: "border-signal-copper/30", label: "DETECTED" },
  acknowledged: { bg: "bg-teal-50", text: "text-signal-cyan", border: "border-signal-cyan/30", label: "ACKNOWLEDGED" },
  crew_assigned: { bg: "bg-teal-50", text: "text-signal-cyan", border: "border-signal-cyan/30", label: "CREW ASSIGNED" },
  resolved: { bg: "bg-slate-100", text: "text-slate-600", border: "border-slate-300", label: "RESOLVED · UNVERIFIED" },
  verified: { bg: "bg-emerald-50", text: "text-signal-live", border: "border-signal-live/30", label: "VERIFIED" },
  closed: { bg: "bg-slate-50", text: "text-slate-400", border: "border-slate-200", label: "CLOSED" },
};

/* ── Auto-fit map to incident locations or all poles ── */
function AutoFit({ incidents, poles }) {
  const map = useMap();
  useEffect(() => {
    const activeInc = incidents.filter((i) => !["verified", "closed"].includes(i.status) && i.lat && i.lon);
    if (activeInc.length > 0) {
      const bounds = activeInc.map((i) => [i.lat, i.lon]);
      try {
        map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
      } catch { /* ignore if single point */ }
    } else if (poles.length > 0) {
      const lats = poles.map((p) => p.lat);
      const lons = poles.map((p) => p.lon);
      map.fitBounds(
        [[Math.min(...lats), Math.min(...lons)], [Math.max(...lats), Math.max(...lons)]],
        { padding: [40, 40] }
      );
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // only on mount

  return null;
}

/* ── Pulse ring for incident markers ── */
function IncidentPulse({ center, onClick, inc }) {
  return (
    <>
      {/* Outer pulse ring */}
      <CircleMarker
        center={center}
        radius={16}
        pathOptions={{
          color: "#c87a1a",
          fillColor: "#c87a1a",
          fillOpacity: 0.1,
          weight: 1.5,
          dashArray: "4 3",
        }}
      />
      {/* Inner marker */}
      <CircleMarker
        center={center}
        radius={10}
        pathOptions={{
          color: "#c87a1a",
          fillColor: "#c87a1a",
          fillOpacity: 0.25,
          weight: 2,
        }}
        eventHandlers={{ click: onClick }}
      />
    </>
  );
}

/* ── Transformer marker ── */
function TransformerMarker({ center, dtId, poleCount }) {
  return (
    <CircleMarker
      center={center}
      radius={7}
      pathOptions={{
        color: "#ffffff",
        fillColor: DT_COLOR,
        fillOpacity: 0.9,
        weight: 1.5,
      }}
    >
      <Tooltip direction="top" opacity={0.95}>
        <div className="font-data text-xs space-y-0.5">
          <div className="font-semibold">{dtId}</div>
          <div>{poleCount} poles</div>
        </div>
      </Tooltip>
    </CircleMarker>
  );
}

/* ── Floating incident detail card (overlays the map) ── */
function IncidentOverlay({ inc, onClose, onOpenDrawer }) {
  const [detail, setDetail] = useState(null);

  useEffect(() => {
    if (!inc) return;
    let alive = true;
    api.incident(inc.id).then((d) => { if (alive) setDetail(d); });
    const t = setInterval(() => {
      api.incident(inc.id).then((d) => { if (alive) setDetail(d); });
    }, 4000);
    return () => { alive = false; clearInterval(t); };
  }, [inc?.id]);

  if (!inc) return null;

  const st = STATUS_COLORS[inc.status] || STATUS_COLORS.detected;
  const d = detail || inc;

  function locationLabel() {
    if (d.type === "span") return `Span: ${d.span_from_pole_id ?? d.dt_id} → ${d.span_to_pole_id}`;
    if (d.type === "dt") return `Transformer ${d.dt_id} (entire DT)`;
    if (d.type === "feeder") return `Feeder ${d.feeder_id} (entire feeder)`;
    return d.dt_id || d.feeder_id || "—";
  }

  return (
    <div
      className="absolute top-4 right-14 z-[1001] w-[360px] bg-white/98 border border-panel-700 rounded-xl shadow-xl backdrop-blur-sm overflow-hidden"
      style={{ animation: "overlay-slide-in 0.3s cubic-bezier(0.16, 1, 0.3, 1)" }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-panel-700 bg-panel-950">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`shrink-0 border rounded px-2 py-0.5 text-[10px] font-data tracking-wide ${st.bg} ${st.text} ${st.border}`}>
            {st.label}
          </span>
          <span className="font-data text-xs text-slate-700 font-medium truncate">{d.id}</span>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-700 text-lg leading-none transition-colors ml-2 shrink-0"
        >
          ×
        </button>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-3 max-h-[480px] overflow-y-auto">
        {/* Location */}
        <div>
          <div className="text-[10px] tracking-widest text-slate-400 mb-1">LOCATION</div>
          <div className="text-sm text-slate-800 font-medium">{locationLabel()}</div>
          <div className="text-xs text-slate-500 mt-0.5">
            {d.pincode && <>PIN {d.pincode} · </>}
            {d.type?.toUpperCase()} · Feeder {d.feeder_id} · DT {d.dt_id}
          </div>
        </div>

        {/* Impact */}
        <div className="flex gap-5">
          <div>
            <div className="font-data text-lg text-slate-800 font-semibold">{d.poles_affected}</div>
            <div className="text-[10px] text-slate-400 tracking-wide">POLES</div>
          </div>
          <div>
            <div className="font-data text-lg text-slate-800 font-semibold">~{d.households_affected_estimate}</div>
            <div className="text-[10px] text-slate-400 tracking-wide">HOUSEHOLDS</div>
          </div>
          <div className="ml-auto">
            <ConfidenceMeter label={d.confidence_label} value={d.confidence} />
          </div>
        </div>

        {/* Confidence reasons */}
        {d.confidence_reasons && d.confidence_reasons.length > 0 && (
          <div>
            <div className="text-[10px] tracking-widest text-slate-400 mb-1">CONFIDENCE FACTORS</div>
            <ul className="space-y-1">
              {d.confidence_reasons.map((r, i) => (
                <li key={i} className="text-[11px] text-slate-600 flex gap-1.5 items-start">
                  <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${
                    r.startsWith("+") ? "bg-signal-live" : r.startsWith("−") || r.startsWith("-") ? "bg-signal-dark" : "bg-slate-400"
                  }`} />
                  {r}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* AI Dispatch Brief */}
        {detail?.ai_briefing && (
          <div>
            <div className="text-[10px] tracking-widest text-slate-400 mb-1">
              DISPATCH NOTE{detail.ai_briefing_source === "template-fallback" ? " (TEMPLATE)" : " · AI"}
            </div>
            <p className="text-sm text-slate-700 leading-relaxed bg-panel-950 rounded-lg px-3 py-2.5 border border-panel-700">
              {detail.ai_briefing}
            </p>
          </div>
        )}

        {/* Topology */}
        <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
          <span>Topology:</span>
          <span className={d.topology_source === "known" ? "text-signal-live" : "text-signal-copper"}>
            {d.topology_source === "known" ? "surveyed ✓" : d.topology_source === "inferred" ? "inferred ⚠" : d.topology_source}
          </span>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-panel-700 bg-panel-950">
        <button
          onClick={onOpenDrawer}
          className="text-xs font-medium text-signal-copper hover:text-signal-copperdim transition-colors"
        >
          Open full details →
        </button>
        <span className="text-[10px] font-data text-slate-400">
          {d.lat?.toFixed(4)}, {d.lon?.toFixed(4)}
        </span>
      </div>
    </div>
  );
}

/* ── Layer filter control panel ── */
function LayerControl({ layers, onToggle, feeders, selectedFeeder, onFeederChange }) {
  return (
    <div className="absolute top-4 left-14 bg-white/95 border border-panel-700 rounded-lg px-3.5 py-3 text-[11px] space-y-2 z-[1000] shadow-sm backdrop-blur-sm" style={{ minWidth: 180 }}>
      <div className="text-[10px] tracking-widest text-slate-400 font-medium mb-1">MAP LAYERS</div>
      {[
        { key: "poles", label: "Poles", color: POLE_COLOR.live },
        { key: "transformers", label: "Transformers", color: DT_COLOR },
        { key: "topologyLines", label: "Topology Lines", color: "#94a3b8" },
        { key: "incidents", label: "Incidents", color: "#c87a1a" },
      ].map((item) => (
        <label key={item.key} className="flex items-center gap-2 cursor-pointer text-slate-600 hover:text-slate-800 transition-colors">
          <input
            type="checkbox"
            checked={layers[item.key]}
            onChange={() => onToggle(item.key)}
            className="accent-signal-copper w-3.5 h-3.5"
          />
          <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: item.color }} />
          {item.label}
        </label>
      ))}

      <div className="border-t border-panel-700 pt-2 mt-2">
        <label className="flex items-center gap-2 cursor-pointer text-slate-600 hover:text-slate-800 transition-colors mb-2">
          <input
            type="checkbox"
            checked={layers.offlineOnly}
            onChange={() => onToggle("offlineOnly")}
            className="accent-signal-dark w-3.5 h-3.5"
          />
          <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: POLE_COLOR.dark }} />
          Offline Poles Only
        </label>

        <div className="text-[10px] tracking-widest text-slate-400 font-medium mb-1">FEEDER FILTER</div>
        <select
          value={selectedFeeder}
          onChange={(e) => onFeederChange(e.target.value)}
          className="w-full bg-panel-950 border border-panel-700 rounded px-1.5 py-1 text-xs text-slate-600 focus:outline-none focus:border-signal-copper"
        >
          <option value="">All feeders</option>
          {feeders.map((f) => (
            <option key={f} value={f}>{f}</option>
          ))}
        </select>
      </div>
    </div>
  );
}

/* ── Visible poles: only render poles within the current map viewport ── */
function VisiblePoles({ poles }) {
  const map = useMap();
  const [visiblePoles, setVisiblePoles] = useState([]);

  useEffect(() => {
    function updateVisible() {
      const bounds = map.getBounds();
      const zoom = map.getZoom();
      // Only render individual poles when zoomed in close (>= 14) for performance & visual clarity
      if (zoom < 14) {
        setVisiblePoles([]);
        return;
      }
      const visible = poles.filter((p) => bounds.contains([p.lat, p.lon]));
      setVisiblePoles(visible);
    }
    updateVisible();
    map.on("moveend", updateVisible);
    map.on("zoomend", updateVisible);
    return () => {
      map.off("moveend", updateVisible);
      map.off("zoomend", updateVisible);
    };
  }, [map, poles]);

  return visiblePoles.map((p) => (
    <CircleMarker
      key={p.pole_id}
      center={[p.lat, p.lon]}
      radius={p.has_device ? 5 : 3}
      pathOptions={{
        color: poleColor(p),
        fillColor: poleColor(p),
        fillOpacity: p.energized === false ? 1 : 0.8,
        weight: p.energized === false ? 1.5 : 0.5,
      }}
    >
      <Tooltip direction="top" opacity={0.95}>
        <div className="font-data text-xs space-y-0.5">
          <div className="font-semibold">{p.pole_id}</div>
          <div>Status: <span style={{ color: poleColor(p), fontWeight: 600 }}>{poleStatusText(p)}</span></div>
          <div className="text-slate-500">DT: {p.dt_id}</div>
          <div className="text-slate-500">Feeder: {p.feeder_id}</div>
          {p.last_received_at && (
            <div className="text-slate-400">Last seen: {timeAgoShort(p.last_received_at)}</div>
          )}
          <div className="text-slate-400">
            Topology: {p.topology_source === "known" ? "surveyed" : p.topology_source === "inferred" ? "inferred" : "unknown"}
          </div>
        </div>
      </Tooltip>
    </CircleMarker>
  ));
}

/* ── Visible topology lines: only render within the current map viewport ── */
function VisibleTopologyLines({ topologyLines }) {
  const map = useMap();
  const [visibleLines, setVisibleLines] = useState([]);

  useEffect(() => {
    function updateVisible() {
      const bounds = map.getBounds();
      const zoom = map.getZoom();
      if (zoom < 12) {
        setVisibleLines([]);
        return;
      }
      const visible = topologyLines.filter((line) => {
        return line.positions.some((pos) => bounds.contains(pos));
      });
      setVisibleLines(visible);
    }
    updateVisible();
    map.on("moveend", updateVisible);
    map.on("zoomend", updateVisible);
    return () => {
      map.off("moveend", updateVisible);
      map.off("zoomend", updateVisible);
    };
  }, [map, topologyLines]);

  return visibleLines.map((line, i) => (
    <Polyline
      key={`line-${i}`}
      positions={line.positions}
      pathOptions={{ color: line.color, weight: 1.5 }}
    />
  ));
}

export default function MapView({ incidents, onSelect }) {
  const [poles, setPoles] = useState([]);
  const [topologyLines, setTopologyLines] = useState([]);
  const [layers, setLayers] = useState({
    poles: true,
    transformers: true,
    topologyLines: true,
    incidents: true,
    offlineOnly: false,
  });
  const [selectedFeeder, setSelectedFeeder] = useState("");
  const [selectedIncident, setSelectedIncident] = useState(null);

  const toggleLayer = (key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }));

  /* When an incident marker is clicked on the map, show floating overlay */
  const handleIncidentClick = useCallback((inc) => {
    setSelectedIncident(inc);
  }, []);

  /* Load poles */
  useEffect(() => {
    let alive = true;
    async function load() {
      const rows = await api.poles();
      if (alive) setPoles(rows);
    }
    load();
    const t = setInterval(load, 15000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  /* Compute derived data: feeders list, DT centroids, topology lines */
  const feeders = useMemo(() => {
    const set = new Set(poles.map((p) => p.feeder_id).filter(Boolean));
    return [...set].sort();
  }, [poles]);

  const filteredPoles = useMemo(() => {
    let result = poles;
    if (selectedFeeder) {
      result = result.filter((p) => p.feeder_id === selectedFeeder);
    }
    if (layers.offlineOnly) {
      result = result.filter((p) => p.energized === false || !p.has_device);
    }
    return result;
  }, [poles, selectedFeeder, layers.offlineOnly]);

  /* Compute transformer centroids from pole groups */
  const dtMarkers = useMemo(() => {
    const byDt = {};
    for (const p of filteredPoles) {
      if (!byDt[p.dt_id]) byDt[p.dt_id] = { poles: [], feeder_id: p.feeder_id };
      byDt[p.dt_id].poles.push(p);
    }
    return Object.entries(byDt).map(([dtId, data]) => {
      const lats = data.poles.map((p) => p.lat);
      const lons = data.poles.map((p) => p.lon);
      const centerLat = lats.reduce((a, b) => a + b, 0) / lats.length;
      const centerLon = lons.reduce((a, b) => a + b, 0) / lons.length;
      return {
        dtId,
        center: [centerLat, centerLon],
        poleCount: data.poles.length,
      };
    });
  }, [filteredPoles]);

  /* Build topology connection lines — use parent_pole_id when available, fall back to nearest neighbor */
  useEffect(() => {
    if (filteredPoles.length === 0) {
      setTopologyLines([]);
      return;
    }

    const byDt = {};
    for (const p of filteredPoles) {
      if (!p.dt_id) continue;
      if (!byDt[p.dt_id]) byDt[p.dt_id] = [];
      byDt[p.dt_id].push(p);
    }

    const connectionLines = [];
    for (const dtId of Object.keys(byDt)) {
      const dtPoles = byDt[dtId];
      if (dtPoles.length < 2) continue;

      // Build a lookup for fast access
      const lookup = {};
      for (const p of dtPoles) lookup[p.pole_id] = p;

      // Try to use resolved_parent links first (much faster than nearest-neighbor)
      let usedParentLinks = false;
      for (const p of dtPoles) {
        const parentId = p.resolved_parent_pole_id;
        if (parentId && lookup[parentId]) {
          usedParentLinks = true;
          const parent = lookup[parentId];
          const bothLive = poleColor(p) === POLE_COLOR.live && poleColor(parent) === POLE_COLOR.live;
          const eitherDark = poleColor(p) === POLE_COLOR.dark || poleColor(parent) === POLE_COLOR.dark;
          connectionLines.push({
            positions: [[p.lat, p.lon], [parent.lat, parent.lon]],
            color: eitherDark ? "rgba(220, 53, 69, 0.35)" : bothLive ? "rgba(22, 163, 122, 0.25)" : "rgba(148, 163, 184, 0.25)",
          });
        }
      }

      // Fallback: simple sequential chain if no parent links exist
      if (!usedParentLinks) {
        // Sort by seq_on_line if available, otherwise by pole_id
        const sorted = [...dtPoles].sort((a, b) => (a.seq_on_line || 0) - (b.seq_on_line || 0) || a.pole_id.localeCompare(b.pole_id));
        for (let i = 1; i < sorted.length; i++) {
          const prev = sorted[i - 1];
          const curr = sorted[i];
          const bothLive = poleColor(prev) === POLE_COLOR.live && poleColor(curr) === POLE_COLOR.live;
          const eitherDark = poleColor(prev) === POLE_COLOR.dark || poleColor(curr) === POLE_COLOR.dark;
          connectionLines.push({
            positions: [[prev.lat, prev.lon], [curr.lat, curr.lon]],
            color: eitherDark ? "rgba(220, 53, 69, 0.35)" : bothLive ? "rgba(22, 163, 122, 0.25)" : "rgba(148, 163, 184, 0.25)",
          });
        }
      }
    }
    setTopologyLines(connectionLines);
  }, [filteredPoles]);

  /* Keep selected incident data fresh */
  const freshSelectedInc = useMemo(() => {
    if (!selectedIncident) return null;
    return incidents.find((i) => i.id === selectedIncident.id) || selectedIncident;
  }, [incidents, selectedIncident]);

  if (poles.length === 0) {
    return (
      <div className="h-full flex items-center justify-center bg-panel-950">
        <div className="text-center">
          <div className="skeleton w-48 h-48 rounded-lg mx-auto mb-4" />
          <div className="text-slate-500 text-sm">Loading network map…</div>
        </div>
      </div>
    );
  }

  const center = [filteredPoles[0]?.lat || poles[0].lat, filteredPoles[0]?.lon || poles[0].lon];

  return (
    <div className="h-full w-full relative">
      <MapContainer center={center} zoom={12} className="h-full w-full" preferCanvas>
        <TileLayer
          attribution='&copy; <a href="https://carto.com/">CARTO</a>'
          url="https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png"
        />

        <AutoFit incidents={incidents} poles={filteredPoles} />

        {/* Topology connection lines — viewport-culled */}
        {layers.topologyLines && <VisibleTopologyLines topologyLines={topologyLines} />}

        {/* Pole markers — viewport-culled */}
        {layers.poles && <VisiblePoles poles={filteredPoles} />}

        {/* Transformer markers */}
        {layers.transformers && dtMarkers.map((dt) => (
          <TransformerMarker
            key={dt.dtId}
            center={dt.center}
            dtId={dt.dtId}
            poleCount={dt.poleCount}
          />
        ))}

        {/* Incident markers with pulse */}
        {layers.incidents && incidents
          .filter((inc) => !["verified", "closed"].includes(inc.status))
          .map((inc) =>
            inc.lat && inc.lon ? (
              <IncidentPulse
                key={inc.id}
                center={[inc.lat, inc.lon]}
                inc={inc}
                onClick={() => handleIncidentClick(inc)}
              />
            ) : null
          )}
      </MapContainer>

      {/* ── Floating incident detail overlay ── */}
      {freshSelectedInc && (
        <IncidentOverlay
          inc={freshSelectedInc}
          onClose={() => setSelectedIncident(null)}
          onOpenDrawer={() => {
            onSelect(freshSelectedInc.id);
            setSelectedIncident(null);
          }}
        />
      )}

      {/* ── Layer control panel ── */}
      <LayerControl
        layers={layers}
        onToggle={toggleLayer}
        feeders={feeders}
        selectedFeeder={selectedFeeder}
        onFeederChange={setSelectedFeeder}
      />

      {/* ── Legend ── */}
      <div className="absolute bottom-4 left-4 bg-white/95 border border-panel-700 rounded-lg px-3.5 py-2.5 text-[11px] space-y-1.5 z-[1000] shadow-sm backdrop-blur-sm text-slate-600">
        <div className="text-[10px] tracking-widest text-slate-400 font-medium mb-1">LEGEND</div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: POLE_COLOR.live }} /> Live pole
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: POLE_COLOR.dark }} /> Dark pole
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: POLE_COLOR.unknown }} /> Silent / unknown
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full" style={{ background: POLE_COLOR.noDevice }} /> No device
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full border-2" style={{ borderColor: DT_COLOR, background: `${POLE_COLOR.live}99` }} /> Transformer
        </div>
        <div className="flex items-center gap-2">
          <span className="w-3 h-3 rounded-full border-2 border-signal-copper bg-signal-copper/20" /> Incident
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 rounded" style={{ background: `${POLE_COLOR.live}66` }} /> Live segment
        </div>
        <div className="flex items-center gap-2">
          <span className="w-4 h-0.5 rounded" style={{ background: `${POLE_COLOR.dark}66` }} /> Dark segment
        </div>
      </div>

      {/* ── Pole count ── */}
      <div className="absolute top-4 right-4 bg-white/95 border border-panel-700 rounded px-3 py-1.5 text-[11px] font-data text-slate-500 z-[1000] shadow-sm">
        {filteredPoles.length} poles{selectedFeeder ? ` (${selectedFeeder})` : ""} · {dtMarkers.length} transformers
      </div>
    </div>
  );
}
