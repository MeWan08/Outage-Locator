const TIERS = {
  high: { bars: 3, color: "bg-signal-live", label: "HIGH" },
  medium: { bars: 2, color: "bg-signal-copper", label: "MEDIUM" },
  low: { bars: 1, color: "bg-signal-dark", label: "LOW" },
};

export default function ConfidenceMeter({ label, value, size = "sm" }) {
  const tier = TIERS[label] || TIERS.low;
  const barHeights = size === "lg" ? ["h-2.5", "h-4", "h-5.5"] : ["h-1.5", "h-2.5", "h-3.5"];
  return (
    <div className="flex items-center gap-1.5" title={`Confidence ${(value * 100).toFixed(0)}%`}>
      <div className="flex items-end gap-0.5">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className={`w-1.5 ${barHeights[i]} rounded-sm ${i < tier.bars ? tier.color : "bg-panel-600"}`}
          />
        ))}
      </div>
      <span className="font-data text-[11px] tracking-wide text-slate-400">
        {tier.label} · {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}
