import { useEffect, useState } from "react";
import { api } from "../api.js";
import ConfidenceMeter from "./ConfidenceMeter.jsx";

function Section({ title, children }) {
  return (
    <div className="px-5 py-4 border-b border-panel-700">
      <div className="text-[10px] tracking-widest text-slate-500 mb-2">{title}</div>
      {children}
    </div>
  );
}

function ActionButton({ children, onClick, tone = "default", disabled }) {
  const tones = {
    default: "bg-panel-700 hover:bg-panel-600 text-slate-200",
    copper: "bg-signal-copper/20 hover:bg-signal-copper/30 text-signal-copper border border-signal-copper/40",
    live: "bg-signal-live/20 hover:bg-signal-live/30 text-signal-live border border-signal-live/40",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 rounded text-xs font-medium transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {children}
    </button>
  );
}

export default function IncidentDrawer({ incidentId, onClose, onChanged }) {
  const [inc, setInc] = useState(null);
  const [events, setEvents] = useState([]);
  const [crewName, setCrewName] = useState("");
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [i, e] = await Promise.all([api.incident(incidentId), api.incidentEvents(incidentId)]);
    setInc(i);
    setEvents(e);
  }

  useEffect(() => {
    if (!incidentId) return;
    setInc(null);
    setToast(null);
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [incidentId]);

  if (!incidentId) return null;

  async function run(action) {
    setBusy(true);
    setToast(null);
    try {
      await action();
      await refresh();
      onChanged?.();
    } catch (err) {
      setToast({ tone: "err", text: String(err.message || err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 w-[420px] bg-panel-850 border-l border-panel-700 shadow-2xl flex flex-col z-30">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-panel-700">
        <div className="font-data text-sm text-slate-300">{incidentId}</div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">
          ×
        </button>
      </div>

      {!inc ? (
        <div className="p-8 text-center text-slate-500 text-sm">Loading…</div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          <Section title="LOCATION">
            <div className="text-sm text-slate-200 mb-1">
              {inc.type === "span" && (
                <>
                  Span between <span className="font-data">{inc.span_from_pole_id ?? inc.dt_id}</span> and{" "}
                  <span className="font-data">{inc.span_to_pole_id}</span>
                </>
              )}
              {inc.type === "dt" && <>Transformer {inc.dt_id} (entire transformer down)</>}
              {inc.type === "feeder" && <>Feeder {inc.feeder_id} (entire feeder down)</>}
            </div>
            <div className="text-xs text-slate-500">
              {inc.pincode && <>PIN {inc.pincode} · </>}
              {inc.lat?.toFixed(5)}, {inc.lon?.toFixed(5)}
            </div>
            {inc.candidate_range_pole_ids?.length > 1 && (
              <div className="mt-2 text-xs text-signal-copper">
                Boundary uncertain — could be anywhere across: {inc.candidate_range_pole_ids.join(" → ")}
              </div>
            )}
          </Section>

          <Section title="IMPACT">
            <div className="flex gap-6">
              <div>
                <div className="font-data text-xl text-slate-200">{inc.poles_affected}</div>
                <div className="text-[10px] text-slate-500 tracking-wide">POLES</div>
              </div>
              <div>
                <div className="font-data text-xl text-slate-200">~{inc.households_affected_estimate}</div>
                <div className="text-[10px] text-slate-500 tracking-wide">HOUSEHOLDS (EST.)</div>
              </div>
            </div>
          </Section>

          <Section title="CONFIDENCE">
            <ConfidenceMeter label={inc.confidence_label} value={inc.confidence} size="lg" />
            <ul className="mt-3 space-y-1.5">
              {inc.confidence_reasons.map((r, i) => (
                <li key={i} className="text-xs text-slate-400 flex gap-2">
                  <span className="text-slate-600">·</span>
                  {r}
                </li>
              ))}
            </ul>
            <div className="mt-2 text-[10px] text-slate-500">
              Topology: {inc.topology_source === "known" ? "surveyed" : inc.topology_source === "inferred" ? "geometrically inferred" : inc.topology_source}
            </div>
          </Section>

          {inc.ai_briefing && (
            <Section title={`DISPATCH NOTE${inc.ai_briefing_source === "template-fallback" ? " (TEMPLATE)" : ""}`}>
              <p className="text-sm text-slate-300 leading-relaxed">{inc.ai_briefing}</p>
            </Section>
          )}

          <Section title="ACTIONS">
            <div className="flex flex-wrap gap-2">
              <ActionButton disabled={busy || inc.status !== "detected"} onClick={() => run(() => api.acknowledge(inc.id))}>
                Acknowledge
              </ActionButton>
              <ActionButton
                disabled={busy || !["detected", "acknowledged"].includes(inc.status)}
                onClick={() => {
                  const name = crewName.trim() || "Crew-1";
                  return run(() => api.assignCrew(inc.id, name));
                }}
              >
                Assign crew
              </ActionButton>
              <ActionButton
                tone="copper"
                disabled={busy || ["verified", "closed"].includes(inc.status)}
                onClick={() =>
                  run(async () => {
                    const r = await api.resolve(inc.id);
                    setToast({ tone: r.poles_still_dark > 0 ? "warn" : "ok", text: r.message });
                  })
                }
              >
                Mark resolved
              </ActionButton>
              <ActionButton
                tone="live"
                disabled={busy || inc.status !== "verified"}
                onClick={() => run(() => api.close(inc.id))}
              >
                Close
              </ActionButton>
            </div>
            <input
              value={crewName}
              onChange={(e) => setCrewName(e.target.value)}
              placeholder="Crew name (optional, e.g. Crew-4)"
              className="mt-2 w-full bg-panel-900 border border-panel-600 rounded px-2 py-1.5 text-xs text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-signal-copper"
            />
            {toast && (
              <div
                className={`mt-2 text-xs rounded px-2 py-1.5 border ${
                  toast.tone === "err"
                    ? "border-signal-dark/40 text-signal-dark bg-signal-dark/10"
                    : toast.tone === "warn"
                    ? "border-signal-copper/40 text-signal-copper bg-signal-copper/10"
                    : "border-signal-live/40 text-signal-live bg-signal-live/10"
                }`}
              >
                {toast.text}
              </div>
            )}
            {inc.status === "verified" && (
              <div className="mt-2 text-[11px] text-signal-live">
                ✓ Telemetry-confirmed restored at {inc.verified_at?.replace("T", " ").slice(0, 19)}
              </div>
            )}
          </Section>

          <Section title="AUDIT TRAIL">
            <ul className="space-y-2">
              {events.map((e, i) => (
                <li key={i} className="text-xs">
                  <div className="flex gap-2 items-baseline">
                    <span className="font-data text-slate-500 text-[10px]">{e.at?.replace("T", " ").slice(5, 19)}</span>
                    <span className={e.actor === "system" ? "text-signal-cyan" : "text-slate-300"}>{e.action}</span>
                  </div>
                  {e.note && <div className="text-slate-500 ml-[62px]">{e.note}</div>}
                </li>
              ))}
            </ul>
          </Section>
        </div>
      )}
    </div>
  );
}
