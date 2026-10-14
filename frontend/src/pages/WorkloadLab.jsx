import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { toast } from "sonner";

function YcsbRunner({ ycsb, onRefresh }) {
  const [form, setForm] = useState({ workload: "A", record_count: 1000, operation_count: 1000, threads: 1 });
  const [runs, setRuns] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => { (async () => { try { setRuns((await j(() => endpoints.ycsbRuns())).runs || []); } catch {} })(); }, []);
  const run = async () => {
    setBusy(true);
    try {
      const r = await j(() => endpoints.ycsbRun(form));
      toast.success(`REAL YCSB ${r.workload} · ${r.status} · ${r.metrics.overall_throughput_ops_per_sec?.toFixed(0)} ops/s`);
      setRuns((await j(() => endpoints.ycsbRuns())).runs || []);
      onRefresh();
    } catch (e) { toast.error(e.response?.data?.detail || e.message); }
    setBusy(false);
  };
  if (!ycsb?.ycsb_installed) return null;
  return (
    <div className="mt-3 psg-subpanel p-3" data-testid="ycsb-runner">
      <div className="section-heading mb-2">Run Official YCSB (provenance: REAL_YCSB)</div>
      <div className="flex flex-wrap gap-2 items-end text-sm">
        <label className="flex flex-col gap-1"><span className="section-heading">workload</span>
          <select className="psg-btn-ghost" data-testid="ycsb-workload" value={form.workload} onChange={e => setForm({ ...form, workload: e.target.value })}>
            {["A", "B", "C", "D", "E", "F"].map(w => <option key={w}>{w}</option>)}
          </select>
        </label>
        {[["record_count", 1000], ["operation_count", 1000], ["threads", 1]].map(([k]) => (
          <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
            <input type="number" className="psg-btn-ghost font-mono w-28" data-testid={`ycsb-${k}`} value={form[k]} onChange={e => setForm({ ...form, [k]: +e.target.value })} />
          </label>
        ))}
        <button className="psg-btn-primary" disabled={busy} onClick={run} data-testid="ycsb-run-btn">{busy ? "Running YCSB..." : "Run YCSB"}</button>
      </div>
      {runs.length > 0 && (
        <div className="mt-3 overflow-auto max-h-48">
          <table className="w-full text-xs font-mono">
            <thead className="text-[10px] uppercase text-[color:var(--psg-text-2)]">
              <tr><th className="text-left py-1">Run</th><th>Wk</th><th>Status</th><th>Throughput</th><th>Read P99 µs</th><th>Update P99 µs</th><th>Provenance</th></tr>
            </thead>
            <tbody>
              {runs.slice().reverse().map(r => (
                <tr key={r.run_id} className="border-t border-[color:var(--psg-border-soft)]" data-testid={`ycsb-run-${r.run_id}`}>
                  <td className="py-1">{r.run_id}</td><td>{r.workload}</td>
                  <td><Pill tone={r.status === "SUCCESS" ? "good" : "crit"}>{r.status}</Pill></td>
                  <td>{r.metrics.overall_throughput_ops_per_sec?.toFixed(1) ?? "—"} ops/s</td>
                  <td>{r.metrics.read_p99_us ?? "—"}</td>
                  <td>{r.metrics.update_p99_us ?? "—"}</td>
                  <td><Pill tone="aws">{r.provenance}</Pill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CsvUploader() {
  const [datasets, setDatasets] = useState([]);
  const [busy, setBusy] = useState(false);
  const load = async () => { try { setDatasets((await j(() => endpoints.datasets())).datasets || []); } catch {} };
  useEffect(() => { load(); }, []);
  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setBusy(true);
    try {
      const r = await j(() => endpoints.uploadCsv(f));
      toast.success(`Imported ${r.name} · ${r.rows} rows · ${r.nodes.length} nodes`);
      load();
    } catch (err) { toast.error(err.response?.data?.detail || err.message); }
    setBusy(false);
    e.target.value = "";
  };
  return (
    <Section title="CSV Telemetry Import (IMPORTED_CSV)" testid="section-csv-upload">
      <div className="text-xs text-[color:var(--psg-text-2)] mb-2">
        Required columns: <span className="font-mono">node_id, t, read_iops, write_iops, throughput_mbps, cpu, memory, storage, queue_depth, avg_latency_ms, p95_latency_ms, p99_latency_ms, cache_hit_rate, load, hotspot_score</span>. Min 120 rows. The CSV is genuinely consumed by the training pipeline (features → sequences → models).
      </div>
      <input type="file" accept=".csv" onChange={onFile} disabled={busy} data-testid="csv-upload-input" className="text-sm" />
      {datasets.length > 0 && (
        <div className="mt-2 space-y-1">
          {datasets.map(d => (
            <div key={d.name} className="psg-subpanel p-2 text-xs font-mono flex justify-between" data-testid={`csv-dataset-${d.name}`}>
              <span>{d.name}.csv · {d.rows} rows · nodes: {d.nodes.join(",")}</span>
              <Pill tone="info">{d.provenance}</Pill>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

export default function WorkloadLab() {
  const [ycsb, setYcsb] = useState(null);
  const [form, setForm] = useState({
    workload: "B", distribution: "zipfian", record_count: 10000, operation_count: 500000,
    request_rate: 1000, hot_key_traffic_share: 0.55, zipfian_theta: 0.99,
    read_pct: 0.95, update_pct: 0.05, insert_pct: 0, scan_pct: 0, rmw_pct: 0,
    burst_multiplier: 3.0, burst_start: 120, burst_duration: 180,
    seed: 42, num_nodes: 4,
  });
  useEffect(() => { (async () => setYcsb(await j(() => endpoints.ycsbValidate())))(); }, []);
  const start = async () => { await j(() => endpoints.startWorkload(form)); toast.success("Workload started"); };
  const stop = async () => { await j(() => endpoints.stopWorkload()); toast("Stopped"); };
  const reset = async () => { await j(() => endpoints.resetWorkload()); toast("Reset"); };

  const set = (k, v) => setForm({ ...form, [k]: v });
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold" data-testid="workload-title">Dataset & Workload Lab</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">YCSB-compatible workloads · synthetic generator · configurable distributions and bursts.</p>
      </div>
      <Section title="YCSB Status" testid="section-ycsb-status" right={<Pill tone={ycsb?.ycsb_installed ? "good" : "warn"} testid="ycsb-status-badge">{ycsb?.ycsb_installed ? `REAL YCSB ${ycsb.ycsb_version} · CONFIGURED` : "NOT CONFIGURED · SYNTHETIC MODE"}</Pill>}>
        <div className="text-xs text-[color:var(--psg-text-2)] font-mono">{ycsb?.message}</div>
        <div className="mt-1 text-xs font-mono text-[color:var(--psg-text-3)]">Java: {ycsb?.java_version || "—"} · Home: {ycsb?.ycsb_home || "—"}</div>
        <div className="mt-2 flex flex-wrap gap-1.5">{(ycsb?.supported_workloads || []).map(w => <Pill key={w} tone="info">Workload {w}</Pill>)}</div>
        <YcsbRunner ycsb={ycsb} onRefresh={async () => setYcsb(await j(() => endpoints.ycsbValidate()))} />
      </Section>
      <CsvUploader />
      <Section title="Configure Workload" testid="section-workload-form">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
          {[
            ["workload", ["A", "B", "C", "D", "E", "F", "custom"]],
            ["distribution", ["uniform", "zipfian", "latest", "hotkey", "hotspot"]],
          ].map(([k, opts]) => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <select className="psg-btn-ghost" data-testid={`wl-${k}`} value={form[k]} onChange={e => set(k, e.target.value)}>{opts.map(o => <option key={o}>{o}</option>)}</select>
            </label>
          ))}
          {["record_count", "operation_count", "request_rate", "hot_key_traffic_share", "zipfian_theta",
            "read_pct", "update_pct", "insert_pct", "scan_pct", "rmw_pct",
            "burst_multiplier", "burst_start", "burst_duration", "seed", "num_nodes"].map(k => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <input type="number" step="any" className="psg-btn-ghost font-mono" data-testid={`wl-${k}`} value={form[k]} onChange={e => set(k, +e.target.value)} />
            </label>
          ))}
        </div>
        <div className="flex gap-2 mt-4">
          <button className="psg-btn-primary" onClick={start} data-testid="wl-start-btn">Run Workload</button>
          <button className="psg-btn-ghost" onClick={stop} data-testid="wl-stop-btn">Stop</button>
          <button className="psg-btn-ghost" onClick={reset} data-testid="wl-reset-btn">Reset</button>
        </div>
      </Section>
    </div>
  );
}
