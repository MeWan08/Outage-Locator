import { useEffect, useState, useCallback } from "react";
import { api } from "./api.js";
import StatBar from "./components/StatBar.jsx";
import IncidentList from "./components/IncidentList.jsx";
import IncidentDrawer from "./components/IncidentDrawer.jsx";
import MapView from "./components/MapView.jsx";
import SimulatorPanel from "./components/SimulatorPanel.jsx";

const TABS = [
  { id: "incidents", label: "Incidents" },
  { id: "map", label: "Map" },
  { id: "simulator", label: "Simulator" },
];

export default function App() {
  const [tab, setTab] = useState("incidents");
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [inc, st] = await Promise.all([api.incidents(), api.stats()]);
    setIncidents(inc);
    setStats(st);
    setLastUpdated(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div className="h-screen flex flex-col bg-panel-900">
      <header className="flex items-center gap-6 px-5 py-3 border-b border-panel-700 bg-panel-950">
        <div>
          <div className="font-data text-sm tracking-widest text-signal-copper">KSPDB</div>
          <div className="text-[10px] tracking-widest text-slate-500 -mt-0.5">OUTAGE LOCATOR · CONTROL ROOM CONSOLE</div>
        </div>
        <nav className="flex gap-1 ml-4">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3.5 py-1.5 rounded text-xs font-medium transition-colors ${
                tab === t.id ? "bg-signal-copper/20 text-signal-copper" : "text-slate-400 hover:text-slate-200 hover:bg-panel-800"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <StatBar stats={stats} lastUpdated={lastUpdated} />

      <main className="flex-1 overflow-hidden relative">
        {tab === "incidents" && (
          <div className="h-full overflow-y-auto">
            <IncidentList incidents={incidents} selectedId={selectedId} onSelect={setSelectedId} loading={loading} />
          </div>
        )}
        {tab === "map" && <MapView incidents={incidents} onSelect={setSelectedId} />}
        {tab === "simulator" && (
          <div className="h-full overflow-y-auto">
            <SimulatorPanel incidents={incidents} onChanged={refresh} />
          </div>
        )}

        {selectedId && <IncidentDrawer incidentId={selectedId} onClose={() => setSelectedId(null)} onChanged={refresh} />}
      </main>
    </div>
  );
}
