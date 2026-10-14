import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill, severityTone } from "../components/common/UI";
import { LineChart, Line, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

export default function LiveCluster() {
  const [cluster, setCluster] = useState(null);
  const [selected, setSelected] = useState(null);
  const [nodeHist, setNodeHist] = useState([]);
  useEffect(() => {
    const tick = async () => { try { setCluster(await j(() => endpoints.cluster())); } catch {} };
    tick();
    const t = setInterval(tick, 2500);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (!selected) return;
    const tick = async () => {
      const r = await endpoints.telemetry(120);
      const out = [];
      for (const h of r.data.history) if (h.nodes[selected]) out.push({ t: h.t, ...h.nodes[selected] });
      setNodeHist(out);
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => clearInterval(t);
  }, [selected]);
  const nodes = cluster?.nodes || [];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold" data-testid="cluster-title">Live Cluster Topology</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">Node health, per-tier utilization, hotspot risk. Click a node for detail.</p>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {nodes.map(n => {
          const tone = n.hotspot_score >= 0.75 ? "crit" : n.hotspot_score >= 0.55 ? "warn" : "good";
          return (
            <div key={n.node_id} className="node-tile cursor-pointer" onClick={() => setSelected(n.node_id)} data-testid={`node-tile-${n.node_id}`}>
              <div className="flex items-center justify-between">
                <div className="font-bold text-[color:var(--psg-text)]">{n.node_id}</div>
                <Pill tone={n.tier === "S3" ? "aws" : "muted"}>{n.tier}</Pill>
              </div>
              <div className="mt-2 text-xs font-mono text-[color:var(--psg-text-2)] space-y-0.5">
                <div>load <span className="text-[color:var(--psg-text)]">{(n.load*100).toFixed(1)}%</span></div>
                <div>cpu <span className="text-[color:var(--psg-text)]">{(n.cpu*100).toFixed(1)}%</span> · mem {(n.memory*100).toFixed(1)}%</div>
                <div>queue <span className="text-[color:var(--psg-text)]">{n.queue_depth.toFixed(2)}</span> · p99 {n.p99_latency_ms.toFixed(1)}ms</div>
                <div>cache hit {(n.cache_hit_rate*100).toFixed(1)}%</div>
              </div>
              <div className="mt-2 flex items-center justify-between">
                <Pill tone={tone}>{tone === "crit" ? "HOTSPOT" : tone === "warn" ? "STRESSED" : "NOMINAL"}</Pill>
                <span className="text-xs font-mono">score {n.hotspot_score.toFixed(2)}</span>
              </div>
            </div>
          );
        })}
      </div>
      {selected && (
        <Section title={`${selected} · Detail`} testid="section-node-detail" right={<button className="psg-btn-ghost" onClick={() => setSelected(null)}>Close</button>}>
          <div style={{ height: 260, minHeight: 260, minWidth: 0 }}>
            <ResponsiveContainer minWidth={0} minHeight={0}>
              <LineChart data={nodeHist}>
                <CartesianGrid stroke="#EEF2F1" vertical={false} />
                <XAxis dataKey="t" />
                <YAxis />
                <Tooltip contentStyle={{ background: "#172033", border: 0, color: "#fff", fontFamily: 'JetBrains Mono', fontSize: 11 }} />
                <Line type="monotone" dataKey="load" stroke="#315E6E" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="hotspot_score" stroke="#B42318" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="cache_hit_rate" stroke="#107E58" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Section>
      )}
    </div>
  );
}
