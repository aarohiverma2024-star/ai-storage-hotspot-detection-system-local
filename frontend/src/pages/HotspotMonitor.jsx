import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill, severityTone } from "../components/common/UI";
import { toast } from "sonner";

export default function HotspotMonitor() {
  const [hs, setHs] = useState(null);
  useEffect(() => {
    const tick = async () => { try { setHs(await j(() => endpoints.hotspots())); } catch {} };
    tick();
    const t = setInterval(tick, 3000);
    return () => clearInterval(t);
  }, []);
  const mit = async (row, action) => {
    try {
      const partition = 0;
      const r = await j(() => endpoints.simulate({ action, node_id: row.node_id, partition, throttle_pct: 0.25 }));
      toast.success(`${action} simulated · p99 ${r.before.avg_p99.toFixed(1)}→${r.after.avg_p99.toFixed(1)}`);
    } catch (e) { toast.error(`Failed: ${e.message}`); }
  };
  const rows = hs?.rows || [];
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold" data-testid="hotspot-title">Hotspot Monitor</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">Per-node current & predicted hotspots · active model: <span className="font-mono">{hs?.active_model || "none"}</span></p>
      </div>
      <Section title="Predicted Hotspots" testid="section-hotspot-table">
        <div className="overflow-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-[color:var(--psg-text-2)]">
              <tr><th className="py-2">Node</th><th>Tier</th><th>Load</th><th>Score</th><th>Predicted Prob</th><th>Confidence</th><th>Severity</th><th>Actions</th></tr>
            </thead>
            <tbody className="font-mono text-xs">
              {rows.map(r => (
                <tr key={r.node_id} className="border-t border-[color:var(--psg-border-soft)]">
                  <td className="py-2 font-semibold">{r.node_id}</td>
                  <td>{r.tier}</td>
                  <td>{(r.current_load*100).toFixed(1)}%</td>
                  <td>{r.current_hotspot_score.toFixed(3)}</td>
                  <td>{r.predicted_probability != null ? `${(r.predicted_probability*100).toFixed(1)}%` : "—"}</td>
                  <td>{r.confidence_level || "—"}</td>
                  <td><Pill tone={severityTone(r.severity)}>{r.severity}</Pill></td>
                  <td className="space-x-1">
                    <button className="psg-btn-ghost" data-testid={`mitigate-replicate-${r.node_id}`} onClick={() => mit(r, "REPLICATE")}>Replicate</button>
                    <button className="psg-btn-ghost" data-testid={`mitigate-cache-${r.node_id}`} onClick={() => mit(r, "CACHE_PROMOTION")}>Cache</button>
                    <button className="psg-btn-ghost" data-testid={`mitigate-migrate-${r.node_id}`} onClick={() => mit(r, "MIGRATE")}>Migrate</button>
                    <button className="psg-btn-warn" data-testid={`mitigate-throttle-${r.node_id}`} onClick={() => mit(r, "THROTTLE")}>Throttle</button>
                  </td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={8} className="py-6 text-center text-[color:var(--psg-text-3)]">No data yet — start a workload.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
