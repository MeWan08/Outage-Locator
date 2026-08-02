export default function StatBar({ stats, lastUpdated }) {
  const items = [
    { label: "OPEN INCIDENTS", value: stats?.open_incidents ?? "—", accent: "text-signal-copper" },
    { label: "POLES DARK", value: stats?.poles_reporting_dark ?? "—", accent: "text-signal-dark" },
    { label: "TOTAL POLES", value: stats?.total_poles ?? "—", accent: "text-slate-300" },
    { label: "TRANSFORMERS", value: stats?.dt_count ?? "—", accent: "text-slate-300" },
  ];
  return (
    <div className="flex items-center gap-6 px-5 py-3 border-b border-panel-700 bg-panel-850">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-signal-live pulse-copper" />
        <span className="font-data text-xs text-slate-400 tracking-widest">LIVE</span>
      </div>
      {items.map((it) => (
        <div key={it.label} className="flex flex-col leading-tight">
          <span className={`font-data text-lg font-semibold ${it.accent}`}>{it.value}</span>
          <span className="text-[10px] tracking-widest text-slate-500">{it.label}</span>
        </div>
      ))}
      <div className="ml-auto text-[11px] font-data text-slate-500">
        {lastUpdated ? `updated ${lastUpdated.toLocaleTimeString()}` : ""}
      </div>
    </div>
  );
}
