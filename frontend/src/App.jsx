import { useEffect, useState, useCallback, useRef, createContext, useContext } from "react";
import { api } from "./api.js";
import StatBar from "./components/StatBar.jsx";
import IncidentList from "./components/IncidentList.jsx";
import IncidentDrawer from "./components/IncidentDrawer.jsx";
import MapView from "./components/MapView.jsx";
import SimulatorPanel from "./components/SimulatorPanel.jsx";

/* ─── Toast notification context ─── */
const ToastContext = createContext();
export function useToast() { return useContext(ToastContext); }

function ToastContainer({ toasts, onDismiss }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg max-w-sm bg-white/95 backdrop-blur-sm ${
            t.id.endsWith("-exit") ? "toast-exit" : "toast-enter"
          } ${
            t.tone === "error"
              ? "border-signal-dark/40 text-signal-dark"
              : t.tone === "warning"
              ? "border-signal-copper/40 text-signal-copper"
              : t.tone === "info"
              ? "border-signal-cyan/40 text-signal-cyan"
              : "border-signal-live/40 text-signal-live"
          }`}
        >
          <span className="text-sm flex-1">{t.text}</span>
          <button
            onClick={() => onDismiss(t.id)}
            className="text-slate-400 hover:text-slate-600 text-xs ml-2"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}

const TABS = [
  { id: "incidents", label: "Incidents", icon: "🔔" },
  { id: "map", label: "Map", icon: "🗺️" },
  { id: "simulator", label: "Simulator", icon: "⚡" },
];

export default function App() {
  const [tab, setTab] = useState("incidents");
  const [incidents, setIncidents] = useState([]);
  const [stats, setStats] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);
  const prevIncidentIds = useRef(new Set());
  const toastIdRef = useRef(0);

  /* Toast helpers */
  const addToast = useCallback((text, tone = "success", durationMs = 4000) => {
    const id = `toast-${++toastIdRef.current}`;
    setToasts((prev) => [...prev, { id, text, tone }]);
    if (durationMs > 0) {
      setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), durationMs);
    }
    return id;
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  /* Data refresh */
  const refresh = useCallback(async () => {
    try {
      const [inc, st] = await Promise.all([api.incidents(), api.stats()]);

      /* Detect newly-created incidents for toast notifications */
      if (!loading) {
        const newIds = new Set(inc.map((i) => i.id));
        const prevIds = prevIncidentIds.current;
        for (const i of inc) {
          if (!prevIds.has(i.id) && i.status === "detected") {
            addToast(
              `New incident ${i.id} — ${i.type} fault at ${i.dt_id || i.feeder_id}`,
              "warning"
            );
          }
        }
      }
      prevIncidentIds.current = new Set(inc.map((i) => i.id));

      setIncidents(inc);
      setStats(st);
      setLastUpdated(new Date());
      setLoading(false);
    } catch {
      /* silently retry on next tick */
    }
  }, [loading, addToast]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  /* Keyboard shortcuts */
  useEffect(() => {
    function handleKey(e) {
      /* Don't capture when typing in an input */
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.tagName === "SELECT") return;
      if (e.key === "1") setTab("incidents");
      else if (e.key === "2") setTab("map");
      else if (e.key === "3") setTab("simulator");
      else if (e.key === "Escape") setSelectedId(null);
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const openCount = incidents.filter(
    (i) => !["verified", "closed"].includes(i.status)
  ).length;

  const handleOpenIncident = useCallback((id) => {
    setSelectedId(id);
    setTab("incidents");
  }, []);

  return (
    <ToastContext.Provider value={addToast}>
      <div className="h-screen flex flex-col bg-panel-950">
        {/* ── Header ── */}
        <header className="flex items-center gap-6 px-5 py-3 border-b border-panel-700 bg-white shadow-sm">
          <div className="flex items-center gap-2 pr-6 border-r border-panel-700">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-signal-copper">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
              <polyline points="3.27 6.96 12 12.01 20.73 6.96"/>
              <line x1="12" y1="22.08" x2="12" y2="12"/>
            </svg>
            <div>
              <div className="font-bold text-slate-700 text-[13px] tracking-wide">LumenGrid</div>
              <div className="text-[9px] font-medium tracking-[0.2em] text-slate-400 uppercase">
                AI-Powered <span className="mx-0.5 opacity-50">·</span> Intelligence Console
              </div>
            </div>
          </div>
          <nav className="flex gap-1 ml-4">
            {TABS.map((t, idx) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3.5 py-1.5 rounded text-xs font-medium transition-all duration-200 flex items-center gap-2 ${
                  tab === t.id
                    ? "bg-signal-copper/10 text-signal-copper shadow-sm"
                    : "text-slate-500 hover:text-slate-700 hover:bg-panel-800"
                }`}
                title={`${t.label} (${idx + 1})`}
              >
                <span>{t.label}</span>
                {t.id === "incidents" && openCount > 0 && (
                  <span className="tab-badge bg-signal-copper/15 text-signal-copper">
                    {openCount}
                  </span>
                )}
              </button>
            ))}
          </nav>
          <div className="ml-auto hidden sm:flex items-center gap-3 text-[10px] text-slate-400 font-data">
            <span title="Keyboard shortcuts">
              <kbd className="px-1 py-0.5 bg-panel-850 rounded text-[9px] border border-panel-700">1</kbd>
              <kbd className="px-1 py-0.5 bg-panel-850 rounded text-[9px] ml-0.5 border border-panel-700">2</kbd>
              <kbd className="px-1 py-0.5 bg-panel-850 rounded text-[9px] ml-0.5 border border-panel-700">3</kbd>
              <span className="ml-1">tabs</span>
            </span>
            <span>
              <kbd className="px-1 py-0.5 bg-panel-850 rounded text-[9px] border border-panel-700">esc</kbd>
              <span className="ml-1">close</span>
            </span>
          </div>
        </header>

        {/* ── Stat bar ── */}
        <StatBar stats={stats} lastUpdated={lastUpdated} />

        {/* ── Main content with tab transitions ── */}
        <main className="flex-1 overflow-hidden relative">
          <div key={tab} className="h-full tab-enter">
            {tab === "incidents" && (
              <div className="h-full overflow-y-auto">
                <IncidentList
                  incidents={incidents}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                  loading={loading}
                />
              </div>
            )}
            {tab === "map" && <MapView incidents={incidents} onSelect={handleOpenIncident} />}
            {tab === "simulator" && (
              <div className="h-full overflow-y-auto">
                <SimulatorPanel incidents={incidents} onChanged={refresh} />
              </div>
            )}
          </div>

          {/* ── Drawer overlay + panel ── */}
          {selectedId && (
            <>
              <div
                className="fixed inset-0 bg-black/15 z-20 backdrop-enter"
                onClick={() => setSelectedId(null)}
              />
              <IncidentDrawer
                incidentId={selectedId}
                onClose={() => setSelectedId(null)}
                onChanged={refresh}
              />
            </>
          )}
        </main>

        {/* ── Toasts ── */}
        <ToastContainer toasts={toasts} onDismiss={dismissToast} />
      </div>
    </ToastContext.Provider>
  );
}
