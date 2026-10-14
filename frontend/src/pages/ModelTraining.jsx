import React, { useState, useEffect } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { toast } from "sonner";

export default function ModelTraining() {
  const [datasets, setDatasets] = useState([]);
  const [form, setForm] = useState({
    model_kind: "gru", dataset: "simulator", seq_len: 10, horizon_windows: 5, hotspot_threshold: 0.6,
    hidden: 32, layers: 1, dropout: 0.15, lr: 0.001, epochs: 10, batch: 64,
    workload_key: "B", seed: 42, num_nodes: 4, warmup_sim_seconds: 3600,
  });
  useEffect(() => { (async () => { try { setDatasets((await j(() => endpoints.datasets())).datasets || []); } catch {} })(); }, []);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const set = (k, v) => setForm({ ...form, [k]: v });
  const train = async () => {
    setErr(""); setResult(null); setLoading(true);
    try { const r = await j(() => endpoints.trainModel(form)); setResult(r); toast.success(`${form.model_kind.toUpperCase()} trained · F1 ${r.model.metrics.f1}`); }
    catch (e) { setErr(e.response?.data?.detail || e.message); toast.error("Training failed"); }
    setLoading(false);
  };
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold" data-testid="train-title">Model Training</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">Train GRU / LSTM / RF / LR / Threshold / Moving-Average baselines on deterministic simulator traces.</p>
      </div>
      <Section title="Training Config" testid="section-train-form">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          <label className="flex flex-col gap-1"><span className="section-heading">model</span>
            <select className="psg-btn-ghost" data-testid="train-model" value={form.model_kind} onChange={e => set("model_kind", e.target.value)}>
              {["gru", "lstm", "rf", "lr", "threshold", "moving_average"].map(x => <option key={x}>{x}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1"><span className="section-heading">dataset</span>
            <select className="psg-btn-ghost" data-testid="train-dataset" value={form.dataset} onChange={e => set("dataset", e.target.value)}>
              <option value="simulator">simulator (SYNTHETIC)</option>
              {datasets.map(d => <option key={d.name} value={`csv:${d.name}`}>csv:{d.name} (IMPORTED_CSV)</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1"><span className="section-heading">workload</span>
            <select className="psg-btn-ghost" data-testid="train-workload" value={form.workload_key} onChange={e => set("workload_key", e.target.value)}>
              {["A", "B", "C", "D", "E", "F"].map(x => <option key={x}>{x}</option>)}
            </select>
          </label>
          {["seq_len", "horizon_windows", "hotspot_threshold", "hidden", "layers", "dropout", "lr", "epochs", "batch", "num_nodes", "warmup_sim_seconds", "seed"].map(k => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <input type="number" step="any" className="psg-btn-ghost font-mono" data-testid={`train-${k}`} value={form[k]} onChange={e => set(k, +e.target.value)} />
            </label>
          ))}
        </div>
        <div className="flex gap-2 mt-4">
          <button className="psg-btn-primary" disabled={loading} onClick={train} data-testid="train-run-btn">{loading ? "Training..." : "Train"}</button>
          {err && <div className="text-sm text-[color:var(--psg-crit)] self-center">{err}</div>}
        </div>
      </Section>
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Section title="Metrics" testid="section-train-metrics">
            <div className="grid grid-cols-2 gap-2 text-sm font-mono">
              {Object.entries(result.model.metrics).filter(([k]) => k !== "confusion").map(([k, v]) => (
                <div key={k} className="psg-subpanel p-2 flex justify-between"><span className="text-[color:var(--psg-text-2)]">{k}</span><span>{v}</span></div>
              ))}
              <div className="psg-subpanel p-2 flex justify-between col-span-2"><span>inference_ms</span><span>{result.model.inference_ms}</span></div>
              <div className="psg-subpanel p-2 col-span-2 text-xs">
                Confusion: TP {result.model.metrics.confusion.tp} · FP {result.model.metrics.confusion.fp} · TN {result.model.metrics.confusion.tn} · FN {result.model.metrics.confusion.fn}
              </div>
            </div>
          </Section>
          <Section title="Loss Curves" testid="section-train-loss">
            {result.model.history?.length ? (
              <div style={{ height: 240, minHeight: 240, minWidth: 0 }}>
                <ResponsiveContainer minWidth={0} minHeight={0}>
                  <LineChart data={result.model.history}>
                    <CartesianGrid stroke="#EEF2F1" vertical={false} />
                    <XAxis dataKey="epoch" />
                    <YAxis />
                    <Tooltip contentStyle={{ background: "#172033", border: 0, color: "#fff", fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                    <Legend />
                    <Line type="monotone" dataKey="train_loss" stroke="#315E6E" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="val_loss" stroke="#B42318" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : <div className="text-xs text-[color:var(--psg-text-3)]">No loss curve (non-neural model).</div>}
          </Section>
        </div>
      )}
    </div>
  );
}
