import { useMemo } from "react";

/* ── Radial health gauge ── */
function HealthGauge({ value, label }) {
  const radius = 28;
  const stroke = 4;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(1, value));
  const offset = circumference * (1 - pct);
  const color =
    pct >= 0.98 ? "#16a37a" : pct >= 0.9 ? "#c87a1a" : "#dc3545";

  return (
    <div className="flex items-center gap-3">
      <div className="relative w-16 h-16">
        <svg viewBox="0 0 64 64" className="w-full h-full -rotate-90">
          {/* Background ring */}
          <circle
            cx="32" cy="32" r={radius}
            fill="none" stroke="#d1d6de" strokeWidth={stroke}
          />
          {/* Value ring */}
          <circle
            cx="32" cy="32" r={radius}
            fill="none" stroke={color} strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className="gauge-ring"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="font-data text-sm font-semibold" style={{ color }}>
            {(pct * 100).toFixed(1)}%
          </span>
        </div>
      </div>
      <div className="flex flex-col">
        <span className="text-[10px] tracking-widest text-slate-500">{label}</span>
        <span className="text-xs text-slate-600">
          {pct >= 0.98 ? "Nominal" : pct >= 0.9 ? "Degraded" : "Critical"}
        </span>
      </div>
    </div>
  );
}

/* ── Single stat card ── */
function StatCard({ label, value, accent = "text-slate-700", sub }) {
  return (
    <div className="flex flex-col leading-tight">
      <span className={`font-data text-lg font-semibold ${accent}`}>
        {value ?? "—"}
      </span>
      <span className="text-[10px] tracking-widest text-slate-500">{label}</span>
      {sub && <span className="text-[9px] text-slate-400 mt-0.5">{sub}</span>}
    </div>
  );
}

export default function StatBar({ stats, lastUpdated }) {
  const healthPct = useMemo(() => {
    if (!stats || !stats.total_poles) return 1;
    return Math.max(0, (stats.total_poles - (stats.poles_reporting_dark || 0)) / stats.total_poles);
  }, [stats]);

  return (
    <div className="flex items-center gap-6 px-5 py-3 border-b border-panel-700 bg-white stat-bar-items">
      {/* Live indicator */}
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-signal-live glow-live" />
        <span className="font-data text-xs text-slate-500 tracking-widest">LIVE</span>
      </div>

      {/* Health gauge */}
      <HealthGauge value={healthPct} label="NETWORK HEALTH" />

      {/* Separator */}
      <div className="w-px h-8 bg-panel-700 hidden sm:block" />

      {/* Stat cards */}
      <StatCard
        label="OPEN INCIDENTS"
        value={stats?.open_incidents}
        accent={stats?.open_incidents > 0 ? "text-signal-copper" : "text-signal-live"}
      />
      <StatCard
        label="POLES DARK"
        value={stats?.poles_reporting_dark}
        accent={stats?.poles_reporting_dark > 0 ? "text-signal-dark" : "text-slate-700"}
      />
      <StatCard label="TOTAL POLES" value={stats?.total_poles} />
      <StatCard label="TRANSFORMERS" value={stats?.dt_count} />

      {/* Timestamp */}
      <div className="ml-auto text-[11px] font-data text-slate-400 hidden sm:block">
        {lastUpdated ? (
          <>
            <span className="text-slate-400">updated </span>
            {lastUpdated.toLocaleTimeString()}
          </>
        ) : (
          <span className="skeleton inline-block w-24 h-3" />
        )}
      </div>
    </div>
  );
}
