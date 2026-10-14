import React, { useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";

export default function WhatIf() {
  const [form, setForm] = useState({ request_rate: 1800, zipfian_theta: 1.1, hot_key_traffic_share: 0.7, read_pct: 0.9, num_nodes: 4, seed: 7, steps: 240 });
  const [res, setRes] = useState(null);
  const [loading, setLoading] = useState(false);
  const set = (k, v) => setForm({ ...form, [k]: v });
  const run = async () => { setLoading(true); try { setRes(await j(() => endpoints.whatif(form))); } finally { setLoading(false); } };
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-bold" data-testid="whatif-title">What-If Simulator</h1>
      <p className="text-sm text-[color:var(--psg-text-2)]">Explore how workload skew and rate translate into future hotspot risk.</p></div>
      <Section title="Parameters" testid="section-whatif-form">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {Object.keys(form).map(k => (
            <label key={k} className="flex flex-col gap-1"><span className="section-heading">{k}</span>
              <input type="number" step="any" className="psg-btn-ghost font-mono" data-testid={`wi-${k}`} value={form[k]} onChange={e => set(k, +e.target.value)} />
            </label>
          ))}
        </div>
        <button className="psg-btn-primary mt-4" disabled={loading} onClick={run} data-testid="wi-run-btn">{loading ? "Simulating..." : "Simulate"}</button>
      </Section>
      {res && (
        <Section title="Traces" testid="section-whatif-trace">
          <div style={{ height: 300, minHeight: 300, minWidth: 0 }}>
            <ResponsiveContainer minWidth={0} minHeight={0}>
              <LineChart data={res.trace}>
                <CartesianGrid stroke="#EEF2F1" vertical={false} />
                <XAxis dataKey="t" />
                <YAxis yAxisId="l" />
                <YAxis yAxisId="r" orientation="right" />
                <Tooltip contentStyle={{ background: "#172033", border: 0, color: "#fff", fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                <Legend />
                <Line yAxisId="l" type="monotone" dataKey="load_max" name="Max Load" stroke="#B42318" strokeWidth={2} dot={false} />
                <Line yAxisId="l" type="monotone" dataKey="hotspot_max" name="Max Hotspot Score" stroke="#C26D00" strokeWidth={2} dot={false} />
                <Line yAxisId="r" type="monotone" dataKey="p99_max" name="Max P99 ms" stroke="#315E6E" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Section>
      )}
    </div>
  );
}
