import { useEffect, useState } from "react";
import { MapContainer, TileLayer, CircleMarker, Popup, Tooltip } from "react-leaflet";
import { api } from "../api.js";

const POLE_COLOR = {
  live: "#4fd1a5",
  dark: "#e85d4c",
  unknown: "#6b7684",
};

function poleColor(p) {
  if (!p.has_device) return "#3a424b";
  if (p.energized === true) return POLE_COLOR.live;
  if (p.energized === false) return POLE_COLOR.dark;
  return POLE_COLOR.unknown;
}

export default function MapView({ incidents, onSelect }) {
  const [poles, setPoles] = useState([]);

  useEffect(() => {
    let alive = true;
    async function load() {
      const rows = await api.poles();
      if (alive) setPoles(rows);
    }
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (poles.length === 0) {
    return <div className="p-8 text-center text-slate-500 text-sm">Loading network…</div>;
  }

  const center = [poles[0].lat, poles[0].lon];

  return (
    <div className="h-full w-full relative">
      <MapContainer center={center} zoom={12} className="h-full w-full" preferCanvas>
        <TileLayer
          attribution='&copy; OpenStreetMap contributors'
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        />
        {poles.map((p) => (
          <CircleMarker
            key={p.pole_id}
            center={[p.lat, p.lon]}
            radius={p.has_device ? 3 : 2}
            pathOptions={{ color: poleColor(p), fillColor: poleColor(p), fillOpacity: 0.9, weight: 0 }}
          >
            <Tooltip direction="top" opacity={0.95}>
              <span className="font-data text-xs">
                {p.pole_id} · {p.has_device ? (p.energized === false ? "dark" : p.energized === true ? "live" : "unknown") : "no device"}
              </span>
            </Tooltip>
          </CircleMarker>
        ))}
        {incidents.map((inc) =>
          inc.lat && inc.lon ? (
            <CircleMarker
              key={inc.id}
              center={[inc.lat, inc.lon]}
              radius={10}
              pathOptions={{ color: "#e8a33d", fillColor: "#e8a33d", fillOpacity: 0.25, weight: 2 }}
              eventHandlers={{ click: () => onSelect(inc.id) }}
            >
              <Popup>
                <div className="font-data text-xs">
                  <div className="font-semibold">{inc.id}</div>
                  <div>{inc.type} · {inc.confidence_label} confidence</div>
                  <div>{inc.poles_affected} poles affected</div>
                </div>
              </Popup>
            </CircleMarker>
          ) : null
        )}
      </MapContainer>
      <div className="absolute bottom-4 left-4 bg-panel-850/95 border border-panel-700 rounded px-3 py-2 text-[11px] space-y-1 z-[1000]">
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ background: POLE_COLOR.live }} /> Live</div>
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ background: POLE_COLOR.dark }} /> Dark</div>
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full" style={{ background: POLE_COLOR.unknown }} /> Silent / unknown</div>
        <div className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-panel-600" /> No device</div>
        <div className="flex items-center gap-2"><span className="w-2.5 h-2.5 rounded-full border-2 border-signal-copper" /> Incident</div>
      </div>
    </div>
  );
}
