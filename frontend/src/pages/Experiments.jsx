import React, { useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { toast } from "sonner";

export default function Experiments() {
  const [form, setForm] = useState({ workload_keys: "B,A", model_kinds: "threshold,moving_average,lr,gru", seed: 42, warmup_sim_seconds: 1200, horizon_windows: 5, hotspot_threshold: 0.6 });
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const run = async () => {
    setLoading(true);
    try {
      const body = {
        workload_keys: form.workload_keys.split(",").map(s => s.trim()).filter(Boolean),
        model_kinds: form.model_kinds.split(",").map(s => s.trim()).filter(Boolean),
        seed: +form.seed, warmup_sim_seconds: +form.warmup_sim_seconds,
        horizon_windows: +form.horizon_windows, hotspot_threshold: +form.hotspot_threshold,
      };
      const r = await j(() => endpoints.runExperiments(body));
      setRes(r); toast.success("Experiments complete");
    } catch (e) { toast.error(e.message); } finally { setLoading(false); }
  };
  const set = (k, v) => setForm({ ...form, [k]: v });
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-bold" data-testid="exp-title">Experiment Runner</h1></div>
      <Section title="Configuration" testid="section-exp-form">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          {["workload_keys", "model_kinds"].map(k => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <input className="psg-btn-ghost font-mono" data-testid={`exp-${k}`} value={form[k]} onChange={e => set(k, e.target.value)} />
            </label>
          ))}
          {["seed", "warmup_sim_seconds", "horizon_windows", "hotspot_threshold"].map(k => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <input type="number" step="any" className="psg-btn-ghost font-mono" data-testid={`exp-${k}`} value={form[k]} onChange={e => set(k, e.target.value)} />
            </label>
          ))}
        </div>
        <button disabled={loading} className="psg-btn-primary mt-4" onClick={run} data-testid="exp-run-btn">{loading ? "Running..." : "Run Grid"}</button>
      </Section>
      {res && (
        <Section title="Results" testid="section-exp-results">
          <table className="w-full text-sm font-mono">
            <thead className="text-xs uppercase text-[color:var(--psg-text-2)]">
              <tr><th className="text-left py-2">Workload</th><th>Model</th><th>OK</th><th>Precision</th><th>Recall</th><th>F1</th><th>AUC</th><th>Infer (ms)</th></tr>
            </thead>
            <tbody>
              {res.results.map((r, i) => (
                <tr key={i} className="border-t border-[color:var(--psg-border-soft)]">
                  <td className="py-2">{r.workload}</td><td>{r.model}</td>
                  <td><Pill tone={r.ok ? "good" : "crit"}>{r.ok ? "OK" : "ERR"}</Pill></td>
                  <td>{r.metrics?.precision ?? "—"}</td><td>{r.metrics?.recall ?? "—"}</td>
                  <td>{r.metrics?.f1 ?? "—"}</td><td>{r.metrics?.auc ?? "—"}</td>
                  <td>{r.inference_ms ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}
    </div>
  );
}
