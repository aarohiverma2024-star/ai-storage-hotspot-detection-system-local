import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";

export default function SystemHealth() {
  const [h, setH] = useState(null);
  const [models, setModels] = useState(null);
  const [audit, setAudit] = useState([]);
  useEffect(() => {
    const tick = async () => {
      try { setH(await j(() => endpoints.health())); } catch {}
      try { setModels(await j(() => endpoints.listModels())); } catch {}
      try { setAudit((await j(() => endpoints.audit())).audit || []); } catch {}
    };
    tick(); const t = setInterval(tick, 4000); return () => clearInterval(t);
  }, []);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold" data-testid="health-title">System Health</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Section title="Service" testid="section-svc">
          <div className="text-sm space-y-1 font-mono">
            <div>Status: <Pill tone={h?.status === "ok" ? "good" : "crit"}>{h?.status || "—"}</Pill></div>
            <div>t_sim: <b>{h?.t_sim ?? 0}s</b></div>
            <div>Simulator: <Pill tone={h?.sim_running ? "good" : "muted"}>{h?.sim_running ? "RUNNING" : "IDLE"}</Pill></div>
            <div>YCSB: <Pill tone="warn">{h?.ycsb_status}</Pill></div>
          </div>
        </Section>
        <Section title="Models" testid="section-models-health">
          <div className="text-sm font-mono space-y-1">
            <div>Active: <Pill tone="info">{models?.active || "none"}</Pill></div>
            <div>Registered: <b>{models?.models?.length || 0}</b></div>
            <ul className="text-xs mt-2 space-y-1">
              {(models?.models || []).map(m => <li key={m.name}>· {m.name} — F1 {m.metrics.f1}</li>)}
            </ul>
          </div>
        </Section>
        <Section title="Audit (last 20)" testid="section-audit">
          <div className="text-xs font-mono max-h-56 overflow-auto space-y-1">
            {audit.slice(-20).reverse().map((a, i) => (
              <div key={i} className="psg-subpanel p-2">{new Date(a.ts * 1000).toLocaleTimeString()} · {a.event}</div>
            ))}
            {!audit.length && <div className="text-[color:var(--psg-text-3)]">No events yet.</div>}
          </div>
        </Section>
      </div>
    </div>
  );
}
