import ConfidenceMeter from "./ConfidenceMeter.jsx";

const STATUS_STYLE = {
  detected: { label: "DETECTED", cls: "bg-signal-copper/15 text-signal-copper border-signal-copper/40" },
  acknowledged: { label: "ACKNOWLEDGED", cls: "bg-signal-cyan/15 text-signal-cyan border-signal-cyan/40" },
  crew_assigned: { label: "CREW ASSIGNED", cls: "bg-signal-cyan/15 text-signal-cyan border-signal-cyan/40" },
  resolved: { label: "RESOLVED · UNVERIFIED", cls: "bg-slate-500/15 text-slate-300 border-slate-500/40" },
  verified: { label: "VERIFIED", cls: "bg-signal-live/15 text-signal-live border-signal-live/40" },
  closed: { label: "CLOSED", cls: "bg-panel-700 text-slate-500 border-panel-600" },
};

function timeAgo(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso + "Z").getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  return `${Math.floor(s / 3600)}h ago`;
}

function locationLabel(inc) {
  if (inc.type === "span") return `${inc.span_from_pole_id ?? inc.dt_id} → ${inc.span_to_pole_id}`;
  if (inc.type === "dt") return `Transformer ${inc.dt_id}`;
  if (inc.type === "feeder") return `Feeder ${inc.feeder_id}`;
  return inc.dt_id || inc.feeder_id || "—";
}

const TYPE_LABEL = { span: "SPAN", dt: "TRANSFORMER", feeder: "FEEDER" };

export default function IncidentList({ incidents, selectedId, onSelect, loading }) {
  if (loading && incidents.length === 0) {
    return <div className="p-8 text-center text-slate-500 font-data text-sm">Loading incidents…</div>;
  }
  if (incidents.length === 0) {
    return (
      <div className="p-10 text-center">
        <div className="text-signal-live text-lg mb-1">Network nominal</div>
        <div className="text-slate-500 text-sm">No open incidents. Use the Simulator tab to inject a fault.</div>
      </div>
    );
  }

  const sorted = [...incidents].sort((a, b) => {
    const rank = (s) => (["detected", "acknowledged", "crew_assigned"].includes(s) ? 0 : s === "resolved" ? 1 : 2);
    if (rank(a.status) !== rank(b.status)) return rank(a.status) - rank(b.status);
    if (b.households_affected_estimate !== a.households_affected_estimate)
      return b.households_affected_estimate - a.households_affected_estimate;
    return b.confidence - a.confidence;
  });

  return (
    <div className="divide-y divide-panel-700">
      {sorted.map((inc) => {
        const st = STATUS_STYLE[inc.status] || STATUS_STYLE.detected;
        return (
          <button
            key={inc.id}
            onClick={() => onSelect(inc.id)}
            className={`w-full text-left px-5 py-3.5 flex items-center gap-4 hover:bg-panel-800 transition-colors ${
              selectedId === inc.id ? "bg-panel-800" : ""
            }`}
          >
            <span className={`shrink-0 border rounded px-2 py-0.5 text-[10px] font-data tracking-wide ${st.cls}`}>
              {st.label}
            </span>
            <span className="shrink-0 w-24 text-[10px] font-data tracking-widest text-slate-500">
              {TYPE_LABEL[inc.type] || inc.type}
            </span>
            <span className="flex-1 min-w-0">
              <div className="font-data text-sm text-slate-200 truncate">{locationLabel(inc)}</div>
              <div className="text-xs text-slate-500 truncate">
                {inc.pincode ? `PIN ${inc.pincode} · ` : ""}
                {inc.poles_affected} poles · ~{inc.households_affected_estimate} households
              </div>
            </span>
            <ConfidenceMeter label={inc.confidence_label} value={inc.confidence} />
            <span className="shrink-0 w-16 text-right font-data text-[11px] text-slate-500">
              {timeAgo(inc.first_detected_at)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
