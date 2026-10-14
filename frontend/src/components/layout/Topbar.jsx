import React, { useEffect, useState } from "react";
import { endpoints, j } from "../../lib/api";
import { Play, StopCircle, RotateCcw, Zap } from "lucide-react";
import { toast } from "sonner";

export default function Topbar() {
  const [health, setHealth] = useState(null);
  const [cluster, setCluster] = useState(null);
  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      try { const h = await j(() => endpoints.health()); if (mounted) setHealth(h); } catch {}
      try { const c = await j(() => endpoints.cluster()); if (mounted) setCluster(c); } catch {}
    };
    tick();
    const t = setInterval(tick, 3000);
    return () => { mounted = false; clearInterval(t); };
  }, []);
  const running = !!health?.sim_running;

  const startDemo = async () => { await j(() => endpoints.demoStart()); toast.success("Demo scenario started"); };
  const stop = async () => { await j(() => endpoints.stopWorkload()); toast("Workload stopped"); };
  const reset = async () => { await j(() => endpoints.demoReset()); toast("Environment reset"); };

  return (
    <div data-testid="app-topbar" className="fixed top-0 left-64 right-0 h-14 z-30 flex items-center justify-between px-6 border-b border-[color:var(--psg-border-soft)] bg-white/85 backdrop-blur">
      <div className="flex items-center gap-3">
        <div className="text-sm font-bold tracking-tight text-[color:var(--psg-text)]">Cluster Control Plane</div>
        <span className="psg-pill pill-info font-mono" data-testid="topbar-tsim">t_sim=<span className="ml-1">{cluster?.t_sim ?? 0}s</span></span>
        <span className={`psg-pill ${running ? "pill-good" : "pill-muted"}`} data-testid="topbar-sim-status">{running ? "SIMULATING" : "IDLE"}</span>
        <span className="psg-pill pill-aws" data-testid="topbar-aws-tier">AWS TIER READY</span>
      </div>
      <div className="flex items-center gap-2">
        <button className="psg-btn-ghost flex items-center gap-1.5" onClick={reset} data-testid="topbar-reset-btn"><RotateCcw size={13} />Reset</button>
        <button className="psg-btn-ghost flex items-center gap-1.5" onClick={stop} data-testid="topbar-stop-btn"><StopCircle size={13} />Stop</button>
        <button className="psg-btn-primary flex items-center gap-1.5" onClick={startDemo} data-testid="topbar-demo-btn"><Zap size={13} />Start Demo</button>
      </div>
    </div>
  );
}
