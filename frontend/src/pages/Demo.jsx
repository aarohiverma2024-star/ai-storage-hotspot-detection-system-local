import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { toast } from "sonner";

const STEPS = [
  "Reset environment",
  "Start YCSB-B workload (Zipfian, hot keys, scheduled burst)",
  "Train fast threshold + GRU baseline (short warmup)",
  "Observe rising hotspot scores",
  "Wait for prediction to fire",
  "Explain the top prediction",
  "Ask decision engine",
  "Simulate mitigation (before/after)",
];

export default function Demo() {
  const [step, setStep] = useState(0);
  const [log, setLog] = useState([]);
  const [running, setRunning] = useState(false);
  const [cluster, setCluster] = useState(null);
  useEffect(() => {
    const tick = async () => { try { setCluster(await j(() => endpoints.cluster())); } catch {} };
    tick(); const t = setInterval(tick, 2500); return () => clearInterval(t);
  }, []);

  const log_ = (s) => setLog(l => [...l, `${new Date().toLocaleTimeString()} · ${s}`]);
  const run = async () => {
    setRunning(true); setLog([]); setStep(0);
    try {
      log_("Resetting..."); await j(() => endpoints.demoReset()); setStep(1);
      log_("Starting scenario..."); await j(() => endpoints.demoStart()); setStep(2);
      log_("Training small GRU (this may take ~30s)...");
      const r = await j(() => endpoints.trainModel({ model_kind: "gru", warmup_sim_seconds: 1200, epochs: 6, hidden: 24, seq_len: 8, horizon_windows: 4, hotspot_threshold: 0.55, workload_key: "B", seed: 42, num_nodes: 4 }));
      log_(`GRU trained · F1 ${r.model.metrics.f1}, AUC ${r.model.metrics.auc}`);
      await j(() => endpoints.activateModel(r.model.name));
      setStep(3);
      log_("Waiting for hotspot signals..."); await new Promise(r => setTimeout(r, 4000));
      setStep(4);
      const hs = await j(() => endpoints.hotspots());
      const top = (hs.rows || []).slice().sort((a, b) => (b.predicted_probability || 0) - (a.predicted_probability || 0))[0];
      if (top) {
        log_(`Top predicted: ${top.node_id} · prob ${(top.predicted_probability||0)*100 | 0}% · sev ${top.severity}`);
        setStep(5);
        try { const ex = await j(() => endpoints.explain(top.node_id));
          log_(`Top contributors: ${ex.contributions.slice(0,3).map(c => c.feature).join(", ")}`); } catch (e) { log_("Not enough history for explain yet."); }
        setStep(6);
        const dec = await j(() => endpoints.decide({
          probability: top.predicted_probability || 0.7, confidence: (top.confidence || 0.7),
          lead_time_sec: 300, read_ratio: 0.9, write_ratio: 0.1, access_concentration: 0.6,
          cache_hit_rate: top.cache_hit_rate, node_load: top.current_load,
          cluster_headroom: Math.min(...(cluster?.nodes || []).map(n => n.load), 0.5),
        }));
        log_(`Decision: ${dec.action} — ${dec.reason}`);
        setStep(7);
        const sim = await j(() => endpoints.simulate({ action: dec.action === "MONITOR" ? "CACHE_PROMOTION" : dec.action, node_id: top.node_id, partition: 0, throttle_pct: 0.25 }));
        log_(`Mitigation p99 ${sim.before.avg_p99.toFixed(1)} → ${sim.after.avg_p99.toFixed(1)}, CV ${sim.before.cluster_load_cv.toFixed(3)} → ${sim.after.cluster_load_cv.toFixed(3)}`);
      } else { log_("No predictions yet."); }
      toast.success("Demo complete");
    } catch (e) { toast.error(e.message); log_("Error: " + e.message); }
    setRunning(false);
  };

  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-bold" data-testid="demo-title">Guided Demo</h1>
      <p className="text-sm text-[color:var(--psg-text-2)]">One-click scenario: healthy → skew → predict → explain → decide → mitigate → verify.</p></div>
      <div className="flex gap-2">
        <button className="psg-btn-primary" disabled={running} onClick={run} data-testid="demo-start-btn">{running ? "Running..." : "Start Demo"}</button>
        <button className="psg-btn-ghost" onClick={() => endpoints.demoReset().then(() => toast("Reset"))} data-testid="demo-reset-btn">Reset</button>
      </div>
      <Section title="Progress" testid="section-demo-progress">
        <ol className="space-y-1 text-sm">
          {STEPS.map((s, i) => (
            <li key={i} className="flex items-center gap-2">
              <span className={`w-5 h-5 rounded-full text-xs font-mono flex items-center justify-center ${i < step ? "bg-[#107E58] text-white" : i === step ? "bg-[#315E6E] text-white pulse-dot" : "bg-[#E8EFF1] text-[color:var(--psg-text-2)]"}`}>{i+1}</span>
              <span className={i <= step ? "text-[color:var(--psg-text)]" : "text-[color:var(--psg-text-3)]"}>{s}</span>
            </li>
          ))}
        </ol>
      </Section>
      <Section title="Log" testid="section-demo-log">
        <div className="psg-terminal p-3 text-xs max-h-64 overflow-auto">
          {log.map((l, i) => <div key={i}>{l}</div>)}
        </div>
      </Section>
    </div>
  );
}
