import { useState, useEffect, useRef } from "react";
import ConfidenceMeter from "./ConfidenceMeter.jsx";

const STATUS_STYLE = {
  detected: { label: "DETECTED", cls: "bg-amber-50 text-signal-copper border-signal-copper/30", dot: "bg-signal-copper" },
  acknowledged: { label: "ACKNOWLEDGED", cls: "bg-teal-50 text-signal-cyan border-signal-cyan/30", dot: "bg-signal-cyan" },
  crew_assigned: { label: "CREW ASSIGNED", cls: "bg-teal-50 text-signal-cyan border-signal-cyan/30", dot: "bg-signal-cyan" },
  resolved: { label: "RESOLVED · UNVERIFIED", cls: "bg-slate-100 text-slate-600 border-slate-300", dot: "bg-slate-400" },
  verified: { label: "VERIFIED", cls: "bg-emerald-50 text-signal-live border-signal-live/30", dot: "bg-signal-live" },
  closed: { label: "CLOSED", cls: "bg-slate-50 text-slate-400 border-slate-200", dot: "bg-slate-300" },
};

const SEVERITY_BORDER = {
  feeder: "severity-feeder",
  dt: "severity-dt",
  span: "severity-span",
};

const TYPE_LABEL = { span: "SPAN", dt: "TRANSFORMER", feeder: "FEEDER" };

const FILTER_OPTIONS = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "detected", label: "Detected" },
  { key: "acknowledged", label: "Acknowledged" },
  { key: "crew_assigned", label: "Crew Assigned" },
  { key: "resolved", label: "Resolved" },
  { key: "verified", label: "Verified" },
  { key: "closed", label: "Closed" },
];

/* ── Live-updating relative time ── */
function TimeAgo({ iso }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  const s = Math.max(0, (Date.now() - new Date(iso + "Z").getTime()) / 1000);
  let text;
  if (s < 60) text = `${Math.floor(s)}s ago`;
  else if (s < 3600) text = `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s ago`;
  else text = `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m ago`;

  return <span>{text}</span>;
}

function locationLabel(inc) {
  if (inc.type === "span") return `${inc.span_from_pole_id ?? inc.dt_id} → ${inc.span_to_pole_id}`;
  if (inc.type === "dt") return `Transformer ${inc.dt_id}`;
  if (inc.type === "feeder") return `Feeder ${inc.feeder_id}`;
  return inc.dt_id || inc.feeder_id || "—";
}

/* ── Skeleton rows for loading state ── */
function SkeletonRow() {
  return (
    <div className="px-5 py-3.5 flex items-center gap-4 border-b border-panel-700">
      <span className="skeleton w-24 h-5 shrink-0" />
      <span className="skeleton w-20 h-3 shrink-0" />
      <div className="flex-1 space-y-1.5">
        <span className="skeleton w-48 h-4 block" />
        <span className="skeleton w-32 h-3 block" />
      </div>
      <span className="skeleton w-20 h-4 shrink-0" />
      <span className="skeleton w-14 h-3 shrink-0" />
    </div>
  );
}

export default function IncidentList({ incidents, selectedId, onSelect, loading }) {
  const [filter, setFilter] = useState("all");
  const seenIdsRef = useRef(new Set());

  /* Track known IDs so we can animate new ones */
  useEffect(() => {
    const timer = setTimeout(() => {
      seenIdsRef.current = new Set(incidents.map((i) => i.id));
    }, 800); // mark as seen after animation completes
    return () => clearTimeout(timer);
  }, [incidents]);

  if (loading && incidents.length === 0) {
    return (
      <div>
        <SkeletonRow />
        <SkeletonRow />
        <SkeletonRow />
      </div>
    );
  }

  if (incidents.length === 0) {
    return (
      <div className="p-10 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-signal-live/10 border border-signal-live/20 mb-4">
          <span className="text-signal-live text-2xl">✓</span>
        </div>
        <div className="text-signal-live text-lg font-medium mb-1">Network Nominal</div>
        <div className="text-slate-500 text-sm">
          No open incidents. Use the <span className="text-signal-copper font-medium">Simulator</span> tab to inject a fault.
        </div>
      </div>
    );
  }

  /* Apply filter */
  const filtered = incidents.filter((inc) => {
    if (filter === "all") return true;
    if (filter === "active") return !["verified", "closed"].includes(inc.status);
    return inc.status === filter;
  });

  const sorted = [...filtered].sort((a, b) => {
    const rank = (s) => (["detected", "acknowledged", "crew_assigned"].includes(s) ? 0 : s === "resolved" ? 1 : 2);
    if (rank(a.status) !== rank(b.status)) return rank(a.status) - rank(b.status);
    if (b.households_affected_estimate !== a.households_affected_estimate)
      return b.households_affected_estimate - a.households_affected_estimate;
    return b.confidence - a.confidence;
  });

  return (
    <div>
      {/* ── Filter pills ── */}
      <div className="flex items-center gap-1.5 px-5 py-2.5 border-b border-panel-700 bg-white overflow-x-auto">
        {FILTER_OPTIONS.map((f) => {
          const count =
            f.key === "all"
              ? incidents.length
              : f.key === "active"
              ? incidents.filter((i) => !["verified", "closed"].includes(i.status)).length
              : incidents.filter((i) => i.status === f.key).length;
          return (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-all whitespace-nowrap ${
                filter === f.key
                  ? "bg-signal-copper/10 text-signal-copper"
                  : "text-slate-500 hover:text-slate-700 hover:bg-panel-800"
              }`}
            >
              {f.label}
              {count > 0 && (
                <span className={`ml-1 font-data text-[10px] ${filter === f.key ? "text-signal-copper/70" : "text-slate-400"}`}>
                  {count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Results ── */}
      {sorted.length === 0 ? (
        <div className="p-8 text-center text-slate-500 text-sm">
          No incidents match the selected filter.
        </div>
      ) : (
        <div className="divide-y divide-panel-700">
          {sorted.map((inc) => {
            const st = STATUS_STYLE[inc.status] || STATUS_STYLE.detected;
            const sevClass = SEVERITY_BORDER[inc.type] || "";
            const isNew = !seenIdsRef.current.has(inc.id);

            return (
              <button
                key={inc.id}
                onClick={() => onSelect(inc.id)}
                className={`w-full text-left px-5 py-3.5 flex items-center gap-4 transition-all duration-200 hover:bg-panel-800/60 ${
                  sevClass
                } ${selectedId === inc.id ? "bg-panel-850" : ""} ${
                  isNew ? "incident-enter incident-flash" : ""
                }`}
              >
                {/* Status badge */}
                <span className={`shrink-0 border rounded px-2 py-0.5 text-[10px] font-data tracking-wide flex items-center gap-1.5 ${st.cls}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${st.dot}`} />
                  {st.label}
                </span>

                {/* Type */}
                <span className="shrink-0 w-24 text-[10px] font-data tracking-widest text-slate-400">
                  {TYPE_LABEL[inc.type] || inc.type}
                </span>

                {/* Location */}
                <span className="flex-1 min-w-0">
                  <div className="font-data text-sm text-slate-800 truncate">{locationLabel(inc)}</div>
                  <div className="text-xs text-slate-500 truncate">
                    {inc.pincode ? `PIN ${inc.pincode} · ` : ""}
                    {inc.poles_affected} poles · ~{inc.households_affected_estimate} households
                  </div>
                </span>

                {/* Confidence */}
                <ConfidenceMeter label={inc.confidence_label} value={inc.confidence} />

                {/* Time */}
                <span className="shrink-0 w-20 text-right font-data text-[11px] text-slate-400">
                  <TimeAgo iso={inc.first_detected_at} />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
