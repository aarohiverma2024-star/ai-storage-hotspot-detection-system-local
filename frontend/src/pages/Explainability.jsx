import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { BarChart, Bar, ResponsiveContainer, XAxis, YAxis, Tooltip, Cell } from "recharts";

export default function Explainability() {
  const [cluster, setCluster] = useState(null);
  const [nid, setNid] = useState("");
  const [exp, setExp] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    (async () => {
      try {
        const c = await j(() => endpoints.cluster());
        setCluster(c);
        if (!nid && c.nodes.length) setNid(c.nodes[0].node_id);
      } catch {}
    })();
  }, []);
  const load = async () => {
    setErr("");
    try {
      const r = await j(() => endpoints.explain(nid));
      setExp(r);
    } catch (e) { setErr(e.response?.data?.detail || e.message); }
  };
  const bars = (exp?.contributions || []).slice(0, 12).map(c => ({ ...c, abs: Math.abs(c.contribution) }));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold" data-testid="explain-title">Why Was This Hotspot Predicted?</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">Lightweight feature-perturbation explanation on the active model.</p>
      </div>
      <Section title="Feature Contributions" testid="section-explain">
        <div className="flex items-center gap-2 mb-4">
          <select className="psg-btn-ghost" data-testid="explain-node-select" value={nid} onChange={(e) => setNid(e.target.value)}>
            {(cluster?.nodes || []).map(n => <option key={n.node_id} value={n.node_id}>{n.node_id}</option>)}
          </select>
          <button className="psg-btn-primary" data-testid="explain-run-btn" onClick={load}>Explain</button>
          {exp && <Pill tone="info">baseline P = {(exp.baseline_probability*100).toFixed(1)}%</Pill>}
        </div>
        {err && <div className="text-sm text-[color:var(--psg-crit)] mb-2">{err}</div>}
        {exp && (
          <div style={{ height: 320, minHeight: 320, minWidth: 0 }}>
            <ResponsiveContainer minWidth={0} minHeight={0}>
              <BarChart data={bars} layout="vertical" margin={{ left: 100 }}>
                <XAxis type="number" />
                <YAxis dataKey="feature" type="category" width={120} />
                <Tooltip contentStyle={{ background: "#172033", border: 0, color: "#fff", fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                <Bar dataKey="contribution">{bars.map((b, i) => <Cell key={i} fill={b.contribution >= 0 ? "#B42318" : "#315E6E"} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Section>
    </div>
  );
}
