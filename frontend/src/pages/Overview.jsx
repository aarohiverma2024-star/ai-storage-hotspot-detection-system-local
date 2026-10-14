import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { KpiCard, Section, Pill, severityTone } from "../components/common/UI";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, AreaChart, Area, CartesianGrid, Legend } from "recharts";

export default function Overview() {
  const [cluster, setCluster] = useState(null);
  const [hotspots, setHotspots] = useState(null);
  const [tele, setTele] = useState(null);
  useEffect(() => {
    const tick = async () => {
      try { setCluster(await j(() => endpoints.cluster())); } catch {}
      try { setHotspots(await j(() => endpoints.hotspots())); } catch {}
      try { setTele(await j(() => endpoints.telemetry(120))); } catch {}
    };
    tick();
    const t = setInterval(tick, 2500);
    return () => clearInterval(t);
  }, []);
  const nodes = cluster?.nodes || [];
  const predicted = hotspots?.rows?.filter(r => (r.predicted_probability || 0) > 0.55).length || 0;
  const active = hotspots?.rows?.filter(r => r.current_hotspot_score > 0.55).length || 0;
  const avgP95 = nodes.length ? (nodes.reduce((s, n) => s + n.p95_latency_ms, 0) / nodes.length).toFixed(2) : "—";
  const avgP99 = nodes.length ? (nodes.reduce((s, n) => s + n.p99_latency_ms, 0) / nodes.length).toFixed(2) : "—";
  const cv = cluster ? cluster.cluster_load_cv.toFixed(3) : "—";
  const throughput = nodes.reduce((s, n) => s + n.read_iops + n.write_iops, 0).toFixed(0);
  const series = (tele?.history || []).map(h => ({
    t: h.t,
    load_mean: +(h.cluster_load_mean * 100).toFixed(1),
    p99: +Math.max(...Object.values(h.nodes).map(n => n.p99_latency_ms)).toFixed(2),
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-[color:var(--psg-text)]" data-testid="overview-title">Cluster State & Predictive Risk</h1>
        <p className="text-sm text-[color:var(--psg-text-2)] mt-1">Current → Future Risk → Why → Action → After · Predictive control extending KML observe-and-tune.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard testid="kpi-nodes" label="Nodes" value={`${cluster?.healthy ?? 0}/${cluster?.num_nodes ?? 0}`} sub="HEALTHY" tone="good" />
        <KpiCard testid="kpi-at-risk" label="At Risk" value={cluster?.at_risk ?? 0} sub={active ? "ACTIVE" : "STABLE"} tone={active ? "crit" : "good"} />
        <KpiCard testid="kpi-predicted" label="Predicted Hotspots" value={predicted} sub="NEXT 5–15 min" tone={predicted ? "warn" : "muted"} />
        <KpiCard testid="kpi-throughput" label="Cluster IOPS" value={throughput} sub="ops/sec" tone="info" />
        <KpiCard testid="kpi-p95" label="Avg P95 (ms)" value={avgP95} sub="latency" tone="muted" />
        <KpiCard testid="kpi-p99" label="Avg P99 (ms)" value={avgP99} sub={`CV ${cv}`} tone="muted" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-7">
          <Section title="Cluster Load & P99 Timeline" testid="section-timeline" right={<Pill tone="info">MEASURED</Pill>}>
            <div style={{ height: 260, minHeight: 260, minWidth: 0 }}>
              <ResponsiveContainer minWidth={0} minHeight={0}>
                <AreaChart data={series}>
                  <defs>
                    <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#315E6E" stopOpacity={0.35} /><stop offset="95%" stopColor="#315E6E" stopOpacity={0.02} /></linearGradient>
                  </defs>
                  <CartesianGrid stroke="#EEF2F1" vertical={false} />
                  <XAxis dataKey="t" />
                  <YAxis yAxisId="l" orientation="left" />
                  <YAxis yAxisId="r" orientation="right" />
                  <Tooltip contentStyle={{ background: "#172033", border: 0, color: "#fff", borderRadius: 6, fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                  <Legend />
                  <Area yAxisId="l" type="monotone" dataKey="load_mean" name="Cluster Load %" stroke="#315E6E" fill="url(#g1)" strokeWidth={2} dot={false} />
                  <Line yAxisId="r" type="monotone" dataKey="p99" name="Max P99 ms" stroke="#B42318" strokeWidth={2} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Section>
        </div>
        <div className="col-span-12 lg:col-span-5">
          <Section title="Predicted Hotspots" testid="section-predicted" right={<Pill tone="warn">LEAD-TIME</Pill>}>
            <div className="space-y-2 max-h-[260px] overflow-auto">
              {(hotspots?.rows || []).map(r => (
                <div key={r.node_id} className="flex items-center justify-between px-3 py-2 psg-subpanel">
                  <div>
                    <div className="text-sm font-semibold text-[color:var(--psg-text)]">{r.node_id} <span className="text-xs text-[color:var(--psg-text-3)] font-mono">· {r.tier}</span></div>
                    <div className="text-xs text-[color:var(--psg-text-2)] font-mono">load {(r.current_load*100).toFixed(1)}% · q {r.queue_depth.toFixed(1)} · p99 {r.p99_latency_ms.toFixed(1)}ms</div>
                  </div>
                  <div className="text-right">
                    <div className="font-mono text-sm">{r.predicted_probability != null ? `${(r.predicted_probability*100).toFixed(1)}%` : "—"}</div>
                    <Pill tone={severityTone(r.severity)}>{r.severity}</Pill>
                  </div>
                </div>
              ))}
              {!hotspots?.rows?.length && <div className="text-sm text-[color:var(--psg-text-3)] p-4 text-center">No telemetry yet — start a workload or Demo.</div>}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
