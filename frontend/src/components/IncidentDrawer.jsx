import { useEffect, useState } from "react";
import { api } from "../api.js";
import ConfidenceMeter from "./ConfidenceMeter.jsx";

/* ── Status pipeline steps ── */
const STEPS = [
  { key: "detected", label: "Detected", icon: "🔍" },
  { key: "acknowledged", label: "Acknowledged", icon: "👁" },
  { key: "crew_assigned", label: "Crew Assigned", icon: "🔧" },
  { key: "resolved", label: "Resolved", icon: "🛠" },
  { key: "verified", label: "Verified", icon: "✓" },
  { key: "closed", label: "Closed", icon: "✕" },
];

function StatusStepper({ status }) {
  const currentIdx = STEPS.findIndex((s) => s.key === status);
  return (
    <div className="flex items-center gap-0 px-5 py-3.5 border-b border-panel-700 bg-panel-950 overflow-x-auto">
      {STEPS.map((step, i) => {
        const isDone = i < currentIdx;
        const isCurrent = i === currentIdx;
        return (
          <div key={step.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs transition-all duration-300 ${
                  isDone
                    ? "bg-signal-live/15 text-signal-live border border-signal-live/30"
                    : isCurrent
                    ? "bg-signal-copper/15 text-signal-copper border border-signal-copper/40 ring-2 ring-signal-copper/20"
                    : "bg-panel-800 text-slate-400 border border-panel-700"
                }`}
              >
                {isDone ? "✓" : step.icon}
              </div>
              <span
                className={`text-[9px] mt-1 tracking-wide whitespace-nowrap ${
                  isCurrent ? "text-signal-copper font-medium" : isDone ? "text-signal-live/80" : "text-slate-400"
                }`}
              >
                {step.label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div
                className={`w-6 h-0.5 mx-1 mt-[-14px] transition-colors duration-300 stepper-line ${
                  isDone ? "bg-signal-live/40" : "bg-panel-700"
                }`}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ── Confidence visual breakdown ── */
function ConfidenceBreakdown({ confidence, reasons }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "#16a37a" : pct >= 40 ? "#c87a1a" : "#dc3545";
  const bgColor = pct >= 70 ? "bg-signal-live" : pct >= 40 ? "bg-signal-copper" : "bg-signal-dark";

  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <div className="flex-1 h-2 bg-panel-700 rounded-full overflow-hidden">
          <div
            className={`h-full ${bgColor} rounded-full conf-segment`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <span className="font-data text-sm font-semibold" style={{ color }}>
          {pct}%
        </span>
      </div>
      <ul className="space-y-1.5">
        {reasons.map((r, i) => (
          <li key={i} className="text-xs text-slate-600 flex gap-2 items-start">
            <span className={`mt-1 w-1.5 h-1.5 rounded-full shrink-0 ${
              r.startsWith("+") ? "bg-signal-live" : r.startsWith("−") || r.startsWith("-") ? "bg-signal-dark" : "bg-slate-400"
            }`} />
            {r}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ── Live duration counter ── */
function DurationCounter({ since }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const s = Math.max(0, (Date.now() - new Date(since + "Z").getTime()) / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return (
    <span className="font-data text-xs text-slate-500">
      {h > 0 ? `${h}h ` : ""}{m}m {sec}s
    </span>
  );
}

/* ── Audit timeline event ── */
const EVENT_ICONS = {
  detected: "🔍",
  acknowledged: "👁",
  crew_assigned: "🔧",
  resolved: "🛠",
  verified: "✓",
  closed: "✕",
  superseded: "⇧",
  promoted: "⬆",
  suppressed: "⏸",
};

function TimelineEvent({ event, isLast }) {
  const icon = EVENT_ICONS[event.action] || "•";
  return (
    <div className="flex gap-3">
      {/* Connector line + dot */}
      <div className="flex flex-col items-center">
        <div
          className={`w-6 h-6 rounded-full flex items-center justify-center text-[10px] shrink-0 ${
            event.actor === "system"
              ? "bg-signal-cyan/10 text-signal-cyan border border-signal-cyan/25"
              : "bg-signal-copper/10 text-signal-copper border border-signal-copper/25"
          }`}
        >
          {icon}
        </div>
        {!isLast && <div className="w-px flex-1 bg-panel-700 min-h-[12px]" />}
      </div>
      {/* Content */}
      <div className="pb-3 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className={`text-xs font-medium ${event.actor === "system" ? "text-signal-cyan" : "text-slate-700"}`}>
            {event.action}
          </span>
          <span className="font-data text-[10px] text-slate-400">
            {event.at?.replace("T", " ").slice(5, 19)}
          </span>
        </div>
        {event.note && <div className="text-[11px] text-slate-500 mt-0.5">{event.note}</div>}
      </div>
    </div>
  );
}

function Section({ title, children, className = "" }) {
  return (
    <div className={`px-5 py-4 border-b border-panel-700 ${className}`}>
      <div className="text-[10px] tracking-widest text-slate-400 mb-2">{title}</div>
      {children}
    </div>
  );
}

function ActionButton({ children, onClick, tone = "default", disabled }) {
  const tones = {
    default: "bg-panel-800 hover:bg-panel-700 text-slate-700 border border-panel-700",
    copper: "bg-signal-copper/10 hover:bg-signal-copper/20 text-signal-copper border border-signal-copper/30",
    live: "bg-signal-live/10 hover:bg-signal-live/20 text-signal-live border border-signal-live/30",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`px-3 py-1.5 rounded text-xs font-medium transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed ${tones[tone]}`}
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

  /* Copy incident ID */
  function copyId() {
    navigator.clipboard.writeText(incidentId).then(
      () => setToast({ tone: "ok", text: "Incident ID copied" }),
      () => {}
    );
    setTimeout(() => setToast(null), 2000);
  }

  return (
    <div className="fixed inset-y-0 right-0 w-[440px] drawer-panel bg-white border-l border-panel-700 shadow-xl flex flex-col z-30 drawer-enter">
      {/* ── Header ── */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-panel-700 bg-panel-950">
        <div className="flex items-center gap-2">
          <div className="font-data text-sm text-slate-700 font-medium">{incidentId}</div>
          <button
            onClick={copyId}
            className="text-slate-400 hover:text-slate-600 text-[10px] transition-colors"
            title="Copy incident ID"
          >
            📋
          </button>
        </div>
        <div className="flex items-center gap-3">
          {inc && (
            <span className="text-[10px] text-slate-400">
              open <DurationCounter since={inc.first_detected_at} />
            </span>
          )}
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-lg leading-none transition-colors">
            ×
          </button>
        </div>
      </div>

      {!inc ? (
        <div className="flex-1 space-y-3 p-5">
          <div className="skeleton w-full h-8" />
          <div className="skeleton w-full h-20" />
          <div className="skeleton w-full h-16" />
          <div className="skeleton w-3/4 h-10" />
        </div>
      ) : (
        <>
          {/* ── Status stepper ── */}
          <StatusStepper status={inc.status} />

          <div className="flex-1 overflow-y-auto">
            {/* ── Location ── */}
            <Section title="LOCATION">
              <div className="text-sm text-slate-800 mb-1">
                {inc.type === "span" && (
                  <>
                    Span between <span className="font-data text-signal-copper font-medium">{inc.span_from_pole_id ?? inc.dt_id}</span> and{" "}
                    <span className="font-data text-signal-copper font-medium">{inc.span_to_pole_id}</span>
                  </>
                )}
                {inc.type === "dt" && <>Transformer <span className="font-data text-signal-copper font-medium">{inc.dt_id}</span> (entire transformer down)</>}
                {inc.type === "feeder" && <>Feeder <span className="font-data text-signal-copper font-medium">{inc.feeder_id}</span> (entire feeder down)</>}
              </div>
              <div className="text-xs text-slate-500">
                {inc.pincode && <>PIN {inc.pincode} · </>}
                {inc.lat?.toFixed(5)}, {inc.lon?.toFixed(5)}
              </div>
              {inc.candidate_range_pole_ids?.length > 1 && (
                <div className="mt-2 text-xs text-signal-copper bg-signal-copper/8 rounded px-2 py-1.5 border border-signal-copper/15">
                  ⚠ Boundary uncertain — could be anywhere across: {inc.candidate_range_pole_ids.join(" → ")}
                </div>
              )}
            </Section>

            {/* ── Impact ── */}
            <Section title="IMPACT">
              <div className="flex gap-6">
                <div>
                  <div className="font-data text-xl text-slate-800">{inc.poles_affected}</div>
                  <div className="text-[10px] text-slate-400 tracking-wide">POLES</div>
                </div>
                <div>
                  <div className="font-data text-xl text-slate-800">~{inc.households_affected_estimate}</div>
                  <div className="text-[10px] text-slate-400 tracking-wide">HOUSEHOLDS (EST.)</div>
                </div>
                <div className="ml-auto flex flex-col items-end">
                  <div className="font-data text-xl text-slate-800">
                    <DurationCounter since={inc.first_detected_at} />
                  </div>
                  <div className="text-[10px] text-slate-400 tracking-wide">DURATION</div>
                </div>
              </div>
            </Section>

            {/* ── Confidence ── */}
            <Section title="CONFIDENCE">
              <ConfidenceBreakdown confidence={inc.confidence} reasons={inc.confidence_reasons} />
              <div className="mt-2 text-[10px] text-slate-400">
                Topology: {inc.topology_source === "known" ? "surveyed ✓" : inc.topology_source === "inferred" ? "geometrically inferred ⚠" : inc.topology_source}
              </div>
            </Section>

            {/* ── AI Dispatch note ── */}
            {inc.ai_briefing && (
              <Section title={`DISPATCH NOTE${inc.ai_briefing_source === "template-fallback" ? " (TEMPLATE)" : ""}`}>
                <p className="text-sm text-slate-700 leading-relaxed">{inc.ai_briefing}</p>
              </Section>
            )}

            {/* ── Actions ── */}
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
                className="mt-2 w-full bg-panel-950 border border-panel-700 rounded px-2 py-1.5 text-xs text-slate-700 placeholder:text-slate-400 focus:outline-none focus:border-signal-copper transition-colors"
              />
              {toast && (
                <div
                  className={`mt-2 text-xs rounded px-2 py-1.5 border ${
                    toast.tone === "err"
                      ? "border-signal-dark/30 text-signal-dark bg-red-50"
                      : toast.tone === "warn"
                      ? "border-signal-copper/30 text-signal-copper bg-amber-50"
                      : "border-signal-live/30 text-signal-live bg-emerald-50"
                  }`}
                >
                  {toast.text}
                </div>
              )}
              {inc.status === "verified" && (
                <div className="mt-2 text-[11px] text-signal-live flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-signal-live" />
                  Telemetry-confirmed restored at {inc.verified_at?.replace("T", " ").slice(0, 19)}
                </div>
              )}
            </Section>

            {/* ── Audit trail (timeline) ── */}
            <Section title="AUDIT TRAIL">
              {events.length === 0 ? (
                <div className="text-xs text-slate-400">No events recorded.</div>
              ) : (
                <div className="space-y-0">
                  {events.map((e, i) => (
                    <TimelineEvent key={i} event={e} isLast={i === events.length - 1} />
                  ))}
                </div>
              )}
            </Section>
          </div>
        </>
      )}
    </div>
  );
}
