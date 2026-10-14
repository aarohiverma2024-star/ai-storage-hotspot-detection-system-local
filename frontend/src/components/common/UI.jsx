import React from "react";

export function KpiCard({ label, value, sub, tone = "default", testid }) {
  const toneMap = { good: "pill-good", warn: "pill-warn", crit: "pill-crit", info: "pill-info", default: "pill-muted" };
  return (
    <div className="psg-card p-4" data-testid={testid}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value mt-1">{value}</div>
      {sub && <div className="mt-1"><span className={`psg-pill ${toneMap[tone]}`}>{sub}</span></div>}
    </div>
  );
}

export function Section({ title, right, children, testid }) {
  return (
    <div className="psg-card p-4" data-testid={testid}>
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-bold tracking-tight text-[color:var(--psg-text)] flex items-center gap-2">{title}</h2>
        {right}
      </div>
      {children}
    </div>
  );
}

export function Pill({ tone = "muted", children, testid }) {
  const map = { good: "pill-good", warn: "pill-warn", crit: "pill-crit", info: "pill-info", aws: "pill-aws", muted: "pill-muted" };
  return <span className={`psg-pill ${map[tone] || "pill-muted"}`} data-testid={testid}>{children}</span>;
}

export function severityTone(sev) {
  if (!sev) return "muted";
  const s = sev.toUpperCase();
  if (s === "CRITICAL" || s === "HIGH") return "crit";
  if (s === "MEDIUM") return "warn";
  if (s === "LOW") return "info";
  return "good";
}
