import { useState } from "react";
import { api } from "../api.js";

function Card({ title, children }) {
  return (
    <div className="bg-panel-850 border border-panel-700 rounded-lg p-4">
      <div className="text-[10px] tracking-widest text-slate-500 mb-3">{title}</div>
      {children}
    </div>
  );
}

const btn = "px-3 py-1.5 rounded text-xs font-medium bg-panel-700 hover:bg-panel-600 text-slate-200 transition-colors disabled:opacity-30";
const btnCopper = "px-3 py-1.5 rounded text-xs font-medium bg-signal-copper/20 hover:bg-signal-copper/30 text-signal-copper border border-signal-copper/40 transition-colors disabled:opacity-30";
const input = "bg-panel-900 border border-panel-600 rounded px-2 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-signal-copper w-full";

export default function SimulatorPanel({ incidents, onChanged }) {
  const [dtId, setDtId] = useState("");
  const [feederId, setFeederId] = useState("");
  const [poleId, setPoleId] = useState("");
  const [silent, setSilent] = useState(false);
  const [log, setLog] = useState([]);
  const [scheduleTarget, setScheduleTarget] = useState("");
  const [scheduleScope, setScheduleScope] = useState("dt");
  const [scheduleMinutes, setScheduleMinutes] = useState(20);

  function push(text, tone = "ok") {
    setLog((l) => [{ text, tone, at: new Date() }, ...l].slice(0, 12));
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

  const openIncidents = incidents.filter((i) => !["verified", "closed"].includes(i.status));

  return (
    <div className="p-5 space-y-4 max-w-3xl">
      <Card title="INJECT A FAULT">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <input className={input} placeholder="DT id (e.g. D-0012) — blank = random" value={dtId} onChange={(e) => setDtId(e.target.value)} />
          <input className={input} placeholder="Feeder id (for feeder-level)" value={feederId} onChange={(e) => setFeederId(e.target.value)} />
          <input className={input} placeholder="Pole id (optional, for span)" value={poleId} onChange={(e) => setPoleId(e.target.value)} />
          <label className="flex items-center gap-2 text-xs text-slate-400">
            <input type="checkbox" checked={silent} onChange={(e) => setSilent(e.target.checked)} />
            force silent failure (no dying message)
          </label>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className={btnCopper}
            onClick={() =>
              run(
                () => api.simFault({ kind: "span", dt_id: dtId || undefined, pole_id: poleId || undefined, silent_failure: silent }),
                "Span fault injected"
              )
            }
          >
            Span fault
          </button>
          <button
            className={btnCopper}
            onClick={() => run(() => api.simFault({ kind: "dt", dt_id: dtId || undefined, silent_failure: silent }), "Transformer fault injected")}
            disabled={!dtId}
          >
            Transformer fault
          </button>
          <button
            className={btnCopper}
            onClick={() => run(() => api.simFault({ kind: "feeder", feeder_id: feederId || undefined, silent_failure: silent }), "Feeder fault injected")}
            disabled={!feederId}
          >
            Feeder fault
          </button>
          <button
            className={btn}
            onClick={() => run(() => api.simFault({ kind: "device_only", pole_id: poleId || undefined }), "Device-only fault injected (not a real outage)")}
            disabled={!poleId}
          >
            Device-only fault
          </button>
          <button className={btn} onClick={() => run(() => api.simStorm(3), "Storm: 3 simultaneous faults injected")}>
            Storm mode (×3)
          </button>
        </div>
      </Card>

      <Card title="REPAIR">
        {openIncidents.length === 0 ? (
          <div className="text-xs text-slate-500">No open incidents to repair.</div>
        ) : (
          <ul className="space-y-1.5">
            {openIncidents.map((inc) => (
              <li key={inc.id} className="flex items-center justify-between text-xs">
                <span className="font-data text-slate-400">
                  {inc.id} · {inc.type} · {inc.dt_id || inc.feeder_id}
                </span>
                <button className={btn} onClick={() => run(() => api.simRepair(inc.id), `Repair sent for ${inc.id}`)}>
                  Repair
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="SCHEDULED OUTAGE (LOAD-SHEDDING FEED)">
        <div className="grid grid-cols-3 gap-3 mb-3">
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
          className={btn}
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
        <p className="text-[11px] text-slate-500 mt-2">
          A real fault matching this exact scope will be suppressed from the incident list while the window is active — inject a matching fault afterward to see it.
        </p>
      </Card>

      <Card title="ACTIVITY LOG">
        {log.length === 0 ? (
          <div className="text-xs text-slate-600">No actions yet.</div>
        ) : (
          <ul className="space-y-1 font-data text-[11px]">
            {log.map((l, i) => (
              <li key={i} className={l.tone === "err" ? "text-signal-dark" : "text-slate-400"}>
                [{l.at.toLocaleTimeString()}] {l.text}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
