import { useState, useEffect } from "react";
import { api } from "../api.js";

function Card({ title, subtitle, children, className = "" }) {
  return (
    <div className={`bg-white border border-panel-700 rounded-lg overflow-hidden shadow-sm ${className}`}>
      <div className="px-4 py-3 border-b border-panel-700/50 bg-panel-950">
        <div className="text-[10px] tracking-widest text-slate-500 font-medium">{title}</div>
        {subtitle && <div className="text-xs text-slate-400 mt-0.5">{subtitle}</div>}
      </div>
      <div className="p-4">
        {children}
      </div>
    </div>
  );
}

const input = "bg-panel-950 border border-panel-700 rounded px-2 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-signal-copper transition-colors w-full";

function ScenarioCard({ icon, title, description, onClick, disabled, tone = "copper" }) {
  const toneClasses = {
    copper: "border-signal-copper/20 hover:border-signal-copper/40 hover:bg-signal-copper/5",
    default: "border-panel-700 hover:border-panel-600 hover:bg-panel-850",
    storm: "border-signal-dark/20 hover:border-signal-dark/40 hover:bg-signal-dark/5",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`text-left p-3 rounded-lg border transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed bg-white ${toneClasses[tone]}`}
    >
      <div className="flex items-center gap-2 mb-1">
        <span className="text-sm">{icon}</span>
        <span className="text-xs font-medium text-slate-700">{title}</span>
      </div>
      <div className="text-[11px] text-slate-500 leading-relaxed">{description}</div>
    </button>
  );
}

function LogEntry({ entry }) {
  const iconMap = { ok: "✓", err: "✕", pending: "⟳" };
  const colorMap = {
    ok: "text-signal-live",
    err: "text-signal-dark",
    pending: "text-signal-copper",
  };
  return (
    <li className="flex items-start gap-2 text-[11px]">
      <span className={`${colorMap[entry.tone] || colorMap.ok} mt-0.5`}>
        {iconMap[entry.tone] || "✓"}
      </span>
      <span className="font-data text-slate-400 shrink-0">{entry.at.toLocaleTimeString()}</span>
      <span className={entry.tone === "err" ? "text-signal-dark" : "text-slate-600"}>{entry.text}</span>
    </li>
  );
}

export default function SimulatorPanel({ incidents, onChanged }) {
  const [dtId, setDtId] = useState("");
  const [feederId, setFeederId] = useState("");
  const [poleId, setPoleId] = useState("");
  const [silent, setSilent] = useState(false);
  const [log, setLog] = useState([]);
  const [scheduleTarget, setScheduleTarget] = useState("");
  const [scheduleScope, setScheduleScope] = useState("dt");
  const [scheduleMinutes, setScheduleMinutes] = useState(20);
  const [simStatus, setSimStatus] = useState(null);

  function push(text, tone = "ok") {
    setLog((l) => [{ text, tone, at: new Date() }, ...l].slice(0, 20));
  }

  async function run(fn, okMsg) {
    try {
      const r = await fn();
      push(okMsg || JSON.stringify(r));
      onChanged?.();
    } catch (err) {
      push(String(err.message || err), "err");
    }
  }

  /* Poll simulator status */
  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const s = await api.simStatus();
        if (alive) setSimStatus(s);
      } catch { /* ignore */ }
    }
    load();
    const t = setInterval(load, 5000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const openIncidents = incidents.filter((i) => !["verified", "closed"].includes(i.status));

  return (
    <div className="p-5 space-y-4 max-w-4xl">
      {/* ── Active faults status ── */}
      {simStatus && simStatus.faulted_poles && Object.keys(simStatus.faulted_poles).length > 0 && (
        <Card title="ACTIVE FAULTS" subtitle="Currently faulted elements in the simulator">
          <div className="flex flex-wrap gap-2">
            {Object.entries(simStatus.faulted_poles || {}).map(([poleId, info]) => (
              <span
                key={poleId}
                className="px-2 py-1 rounded text-[10px] font-data bg-red-50 text-signal-dark border border-signal-dark/20"
              >
                {poleId}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* ── Inject fault ── */}
      <Card title="INJECT A FAULT" subtitle="Simulate network failures to test the detection system">
        {/* Input fields */}
        <div className="grid grid-cols-2 gap-3 mb-4 sim-grid">
          <input className={input} placeholder="DT id (e.g. D-0012) — blank = random" value={dtId} onChange={(e) => setDtId(e.target.value)} />
          <input className={input} placeholder="Feeder id (for feeder-level)" value={feederId} onChange={(e) => setFeederId(e.target.value)} />
          <input className={input} placeholder="Pole id (optional, for span)" value={poleId} onChange={(e) => setPoleId(e.target.value)} />
          <label className="flex items-center gap-2 text-xs text-slate-500 cursor-pointer">
            <input
              type="checkbox"
              checked={silent}
              onChange={(e) => setSilent(e.target.checked)}
              className="accent-signal-copper"
            />
            Force silent failure (no dying message)
          </label>
        </div>

        {/* Scenario cards */}
        <div className="grid grid-cols-2 gap-3 sim-grid">
          <ScenarioCard
            icon="⚡"
            title="Span Fault"
            description="A wire breaks between two poles. System detects the exact break location."
            onClick={() =>
              run(
                () => api.simFault({ kind: "span", dt_id: dtId || undefined, pole_id: poleId || undefined, silent_failure: silent }),
                "Span fault injected — incident should appear in ~35s"
              )
            }
          />
          <ScenarioCard
            icon="🔌"
            title="Transformer Fault"
            description="Entire DT goes dark. Should create one ticket, not dozens."
            onClick={() => run(() => api.simFault({ kind: "dt", dt_id: dtId || undefined, silent_failure: silent }), "Transformer fault injected")}
            disabled={!dtId}
          />
          <ScenarioCard
            icon="🏭"
            title="Feeder Fault"
            description="All transformers on a feeder go dark. Highest-level fault."
            onClick={() => run(() => api.simFault({ kind: "feeder", feeder_id: feederId || undefined, silent_failure: silent }), "Feeder fault injected")}
            disabled={!feederId}
          />
          <ScenarioCard
            icon="📡"
            title="Device-Only Fault"
            description="A single sensor dies. Should NOT create an outage ticket."
            onClick={() => run(() => api.simFault({ kind: "device_only", pole_id: poleId || undefined }), "Device-only fault injected (not a real outage)")}
            disabled={!poleId}
            tone="default"
          />
        </div>

        {/* Storm mode */}
        <div className="mt-3">
          <ScenarioCard
            icon="🌩️"
            title="Storm Mode (×3)"
            description="Three simultaneous faults across the network. Tests multi-fault detection and isolation."
            onClick={() => run(() => api.simStorm(3), "Storm: 3 simultaneous faults injected")}
            tone="storm"
          />
        </div>
      </Card>

      {/* ── Repair ── */}
      <Card title="REPAIR" subtitle="Restore power and trigger telemetry verification">
        {openIncidents.length === 0 ? (
          <div className="text-xs text-slate-400 text-center py-2">
            No open incidents to repair. Inject a fault first.
          </div>
        ) : (
          <ul className="space-y-2">
            {openIncidents.map((inc) => (
              <li key={inc.id} className="flex items-center justify-between p-2 rounded bg-panel-950 border border-panel-700">
                <div>
                  <span className="font-data text-xs text-slate-700">{inc.id}</span>
                  <span className="text-[10px] text-slate-400 ml-2">
                    {inc.type.toUpperCase()} · {inc.dt_id || inc.feeder_id} · {inc.status}
                  </span>
                </div>
                <button
                  className="px-3 py-1 rounded text-xs font-medium bg-signal-live/10 hover:bg-signal-live/20 text-signal-live border border-signal-live/25 transition-colors"
                  onClick={() => run(() => api.simRepair(inc.id), `Repair sent for ${inc.id}`)}
                >
                  Repair
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ── Scheduled outage ── */}
      <Card title="SCHEDULED OUTAGE" subtitle="Declare a planned maintenance window (load-shedding feed)">
        <div className="grid grid-cols-3 gap-3 mb-3 sim-grid">
          <select className={input} value={scheduleScope} onChange={(e) => setScheduleScope(e.target.value)}>
            <option value="dt">DT scope</option>
            <option value="feeder">Feeder scope</option>
          </select>
          <input className={input} placeholder="Target id (e.g. D-0012)" value={scheduleTarget} onChange={(e) => setScheduleTarget(e.target.value)} />
          <input
            className={input}
            type="number"
            placeholder="Duration (min)"
            value={scheduleMinutes}
            onChange={(e) => setScheduleMinutes(e.target.value)}
          />
        </div>
        <button
          className="px-3 py-1.5 rounded text-xs font-medium bg-panel-800 hover:bg-panel-700 text-slate-700 border border-panel-700 transition-colors disabled:opacity-30"
          disabled={!scheduleTarget}
          onClick={() =>
            run(async () => {
              const now = new Date();
              const end = new Date(now.getTime() + scheduleMinutes * 60000);
              return api.createScheduledOutage({
                scope: scheduleScope,
                target_id: scheduleTarget,
                start: now.toISOString(),
                end: end.toISOString(),
                reason: "planned maintenance",
              });
            }, `Scheduled outage created for ${scheduleTarget}`)
          }
        >
          Declare scheduled outage now
        </button>
        <p className="text-[11px] text-slate-400 mt-2 leading-relaxed">
          A real fault matching this exact scope will be <span className="text-signal-copper font-medium">suppressed</span> from the incident list while the window is active — inject a matching fault afterward to see it.
        </p>
      </Card>

      {/* ── Activity log ── */}
      <Card title="ACTIVITY LOG" subtitle={`${log.length} entries`}>
        {log.length === 0 ? (
          <div className="text-xs text-slate-400 text-center py-2">
            No actions yet. Try injecting a fault above.
          </div>
        ) : (
          <ul className="space-y-1.5 max-h-60 overflow-y-auto">
            {log.map((l, i) => (
              <LogEntry key={i} entry={l} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
