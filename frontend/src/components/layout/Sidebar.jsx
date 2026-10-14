import React, { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { LayoutDashboard, Server, Flame, Brain, Activity, FlaskConical, GitCompareArrows, PlayCircle, Cpu, TerminalSquare, Sliders, ShieldCheck, HeartPulse } from "lucide-react";
import { endpoints, j } from "../../lib/api";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, testid: "nav-overview" },
  { to: "/cluster", label: "Live Cluster", icon: Server, testid: "nav-cluster" },
  { to: "/hotspots", label: "Hotspot Monitor", icon: Flame, testid: "nav-hotspots" },
  { to: "/explain", label: "Explainability", icon: Brain, testid: "nav-explain" },
  { to: "/mitigation", label: "Mitigation Center", icon: ShieldCheck, testid: "nav-mitigation" },
  { to: "/workloads", label: "Workload Lab", icon: TerminalSquare, testid: "nav-workloads" },
  { to: "/training", label: "Model Training", icon: Cpu, testid: "nav-training" },
  { to: "/compare", label: "Model Comparison", icon: GitCompareArrows, testid: "nav-compare" },
  { to: "/experiments", label: "Experiments", icon: FlaskConical, testid: "nav-experiments" },
  { to: "/whatif", label: "What-If Simulator", icon: Sliders, testid: "nav-whatif" },
  { to: "/health", label: "System Health", icon: HeartPulse, testid: "nav-health" },
  { to: "/demo", label: "Demo Mode", icon: PlayCircle, testid: "nav-demo" },
];

export default function Sidebar() {
  const [ycsbReal, setYcsbReal] = useState(false);
  useEffect(() => {
    (async () => {
      try { const d = await j(() => endpoints.ycsbValidate()); setYcsbReal(!!d.ycsb_installed); } catch {}
    })();
  }, []);
  return (
    <aside data-testid="app-sidebar" style={{ background: "var(--psg-sidebar)" }} className="w-64 min-h-screen text-white flex flex-col fixed left-0 top-0">
      <div className="px-5 py-4 border-b border-white/10">
        <div className="flex items-center gap-2">
          <Activity size={20} className="text-[#AFBCBF]" />
          <div>
            <div className="text-sm font-bold tracking-tight">Predictive Storage</div>
            <div className="text-[11px] text-white/50 -mt-0.5">Guardian · v1.0</div>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <span className="psg-pill pill-good" data-testid="sidebar-status-badge"><span className="w-1.5 h-1.5 rounded-full bg-[#107E58] pulse-dot" />ONLINE</span>
          <span className={`psg-pill ${ycsbReal ? "pill-aws" : "pill-muted"}`} data-testid="sidebar-ycsb-badge">{ycsbReal ? "REAL · YCSB" : "SYNTH · YCSB"}</span>
        </div>
      </div>
      <nav className="flex-1 py-3">
        {NAV.map((n) => {
          const Ic = n.icon;
          return (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} data-testid={n.testid}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2 text-[13px] transition-colors border-l-2 ${isActive ? "bg-white/5 text-white border-[#FF9900]" : "text-white/70 border-transparent hover:text-white hover:bg-white/5"}`
              }>
              <Ic size={15} />
              <span>{n.label}</span>
            </NavLink>
          );
        })}
      </nav>
      <div className="px-5 py-3 border-t border-white/10 text-[10px] text-white/40 font-mono">
        Predict · Explain · Prevent
      </div>
    </aside>
  );
}
