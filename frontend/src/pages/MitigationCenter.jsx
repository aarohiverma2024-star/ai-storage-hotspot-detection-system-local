import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { toast } from "sonner";

export default function MitigationCenter() {
  const [mits, setMits] = useState([]);
  const [form, setForm] = useState({
    action: "MIGRATE",
    node_id: "",
    partition: 3,
    throttle_pct: 0.25,
    lead_time_sec: 45,
    partition_size_mb: 500,
  });
  const [cluster, setCluster] = useState(null);
  const [decisionRes, setDecisionRes] = useState(null);
  const [loadingDecide, setLoadingDecide] = useState(false);

  const load = async () => {
    try {
      const data = await j(() => endpoints.mitigations());
      setMits(data.mitigations || []);
    } catch (e) {
      console.error(e);
    }
  };

  const refreshCluster = async () => {
    try {
      const cl = await j(() => endpoints.cluster());
      setCluster(cl);
      return cl;
    } catch (e) {
      console.error("Failed to fetch cluster state", e);
      return null;
    }
  };

  useEffect(() => {
    load();
    refreshCluster();
    const interval = setInterval(refreshCluster, 4000);
    return () => clearInterval(interval);
  }, []);

  const run = async () => {
    try {
      const dur = decisionRes?.estimated_duration_sec ?? (
        form.action === "CACHE_PROMOTION" ? 1.0 :
        form.action === "THROTTLE" ? 0.2 : 12.0
      );
      const lead = Number(form.lead_time_sec) || 45;
      const buf = decisionRes?.buffer_time_sec ?? (lead - dur);

      const payload = {
        ...form,
        lead_time_sec: lead,
        estimated_duration_sec: dur,
        buffer_time_sec: buf,
        downgraded: decisionRes?.downgraded || false,
        buffer_status: decisionRes?.buffer_status || (buf >= 15 ? "HEALTHY" : "TIGHT"),
      };
      await j(() => endpoints.simulate(payload));
      toast.success(`Executed ${form.action} simulation`);
      load();
      refreshCluster();
    } catch (e) {
      toast.error(e.message || "Failed to simulate mitigation");
    }
  };

  const decide = async (overrideParams = {}) => {
    setLoadingDecide(true);
    try {
      let currentCluster = cluster || (await refreshCluster());
      const nodes = currentCluster?.nodes || [];

      // Sort to identify the hottest node
      const sorted = [...nodes].sort(
        (a, b) => (b.hotspot_score || b.load) - (a.hotspot_score || a.load)
      );

      const targetId = overrideParams.node_id !== undefined ? overrideParams.node_id : form.node_id;
      const node = targetId
        ? nodes.find((n) => n.node_id === targetId) || sorted[0]
        : sorted[0];

      if (!node) {
        toast.error("No storage nodes detected in cluster.");
        return;
      }

      const cluster_headroom = nodes.length > 0 ? Math.min(...nodes.map((n) => n.load)) : 0.3;
      const leadTime = Number(overrideParams.lead_time_sec ?? form.lead_time_sec) || 45;
      const partSize = Number(overrideParams.partition_size_mb ?? form.partition_size_mb) || 500;

      const isLiveLoaded = (node.load >= 0.60 || node.hotspot_score >= 0.50);
      const prob = overrideParams.probability ?? (isLiveLoaded ? Math.max(0.75, node.hotspot_score) : 0.85);
      const conf = overrideParams.confidence ?? Math.min(1.0, prob + 0.15);
      const nodeLoad = overrideParams.node_load ?? (isLiveLoaded ? node.load : 0.82);

      const totalIops = Math.max(1, (node.read_iops || 0) + (node.write_iops || 0));
      const readRatio = overrideParams.read_ratio ?? (isLiveLoaded ? (node.read_iops / totalIops) : 0.75);

      const req = {
        node_id: node.node_id,
        probability: prob,
        confidence: conf,
        lead_time_sec: leadTime,
        partition_size_mb: partSize,
        read_ratio: readRatio,
        write_ratio: 1.0 - readRatio,
        access_concentration: 0.6,
        cache_hit_rate: node.cache_hit_rate || 0.7,
        node_load: nodeLoad,
        cluster_headroom,
      };

      const res = await j(() => endpoints.decide(req));
      setDecisionRes(res);

      if (res?.action && res.action !== "MONITOR") {
        setForm((prev) => ({
          ...prev,
          action: res.action,
          node_id: node.node_id,
          lead_time_sec: leadTime,
          partition_size_mb: partSize,
        }));
      }

      if (res.downgraded) {
        toast.warning(`Buffer Exceeded! Downgraded to ${res.action}`);
      } else {
        toast.success(`Recommended Action: ${res.action} (${res.buffer_status || "OK"})`);
      }
    } catch (e) {
      console.error(e);
      toast.error(e.message || "Failed to analyze decision");
    } finally {
      setLoadingDecide(false);
    }
  };

  const applyPreset = (leadSec, partMb, readPct = 0.75) => {
    setForm((prev) => ({
      ...prev,
      lead_time_sec: leadSec,
      partition_size_mb: partMb,
    }));
    decide({ lead_time_sec: leadSec, partition_size_mb: partMb, read_ratio: readPct });
  };

  return (
    <div className="space-y-5">
      {/* Title & Badge */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-b border-[var(--psg-border-soft)] pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-[var(--psg-text)]" data-testid="mit-title">
              Mitigation Center
            </h1>
            <span className="psg-pill pill-info text-[11px] font-semibold tracking-wide uppercase">
              Dual-Timeframe Engine
            </span>
          </div>
          <p className="text-sm text-[var(--psg-text-2)] mt-1">
            Proactive hotspot mitigation with real-time transfer buffer validation to prevent destructive I/O storms.
          </p>
        </div>
      </div>

      {/* Quick Test Scenarios Bar */}
      <div className="psg-card p-4 bg-white border border-[var(--psg-border-soft)] shadow-sm">
        <div className="flex items-center justify-between mb-2.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-[var(--psg-text)]">Quick Test Scenarios</span>
            <span className="text-xs text-[var(--psg-text-3)]">(Verify Lead Time vs. Transfer Duration)</span>
          </div>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          <button
            onClick={() => applyPreset(300, 500, 0.75)}
            className="flex flex-col p-2.5 rounded-lg border border-[#A3D9C9] bg-[#E6F4EA]/70 hover:bg-[#E6F4EA] transition-all text-left group"
          >
            <span className="text-xs font-bold text-[#107E58] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#107E58]"></span>
              Case 1: Ample Lead Time
            </span>
            <span className="text-[11px] text-[#2D5A47] font-mono mt-1">
              300s Lead → <b className="text-[#107E58]">MIGRATE</b> (Safe)
            </span>
          </button>

          <button
            onClick={() => applyPreset(18, 500, 0.75)}
            className="flex flex-col p-2.5 rounded-lg border border-[#FFD599] bg-[#FFF4E5]/70 hover:bg-[#FFF4E5] transition-all text-left group"
          >
            <span className="text-xs font-bold text-[#C26D00] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#C26D00]"></span>
              Case 2: Buffer Exceeded
            </span>
            <span className="text-[11px] text-[#7A4900] font-mono mt-1">
              18s Lead → <b className="text-[#C26D00]">CACHE Downgrade</b>
            </span>
          </button>

          <button
            onClick={() => applyPreset(45, 5000, 0.75)}
            className="flex flex-col p-2.5 rounded-lg border border-[#FECDCA] bg-[#FEF3F2]/70 hover:bg-[#FEF3F2] transition-all text-left group"
          >
            <span className="text-xs font-bold text-[#B42318] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#B42318]"></span>
              Case 3: Huge 5GB Data
            </span>
            <span className="text-[11px] text-[#7A271A] font-mono mt-1">
              45s Lead, 5GB → <b className="text-[#B42318]">CACHE Downgrade</b>
            </span>
          </button>

          <button
            onClick={() => applyPreset(1, 500, 0.75)}
            className="flex flex-col p-2.5 rounded-lg border border-[#D3DAD8] bg-[#EEF2F1]/70 hover:bg-[#EEF2F1] transition-all text-left group"
          >
            <span className="text-xs font-bold text-[#4E5D6C] flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#7A8A99]"></span>
              Case 4: Critical Depletion
            </span>
            <span className="text-[11px] text-[#4E5D6C] font-mono mt-1">
              1s Lead → <b className="text-[#4E5D6C]">MONITOR</b> (Reactive)
            </span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Left Column: Form & Buffer Recommendation */}
        <div className="space-y-4">
          <Section title="Configure & Analyze Mitigation" testid="section-manual">
            <div className="space-y-3 text-sm">
              <div>
                <label className="section-heading block mb-1">Target Action</label>
                <select
                  className="psg-btn-ghost w-full bg-white font-medium"
                  data-testid="mit-action"
                  value={form.action}
                  onChange={(e) => setForm({ ...form, action: e.target.value })}
                >
                  {["MIGRATE", "REPLICATE", "CACHE_PROMOTION", "THROTTLE"].map((a) => (
                    <option key={a}>{a}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="section-heading block mb-1">Target Storage Node</label>
                <select
                  className="psg-btn-ghost w-full bg-white font-medium text-xs"
                  data-testid="mit-node"
                  value={form.node_id}
                  onChange={(e) => setForm({ ...form, node_id: e.target.value })}
                >
                  <option value="">auto (highest loaded node)</option>
                  {(cluster?.nodes || []).map((n) => (
                    <option key={n.node_id} value={n.node_id}>
                      {n.node_id} — Load: {(n.load * 100).toFixed(0)}% · Hotspot Score: {n.hotspot_score?.toFixed(2)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="section-heading block mb-1">Lead Time (s)</label>
                  <input
                    type="number"
                    className="psg-btn-ghost w-full bg-white font-mono"
                    data-testid="mit-lead-time"
                    value={form.lead_time_sec}
                    onChange={(e) => setForm({ ...form, lead_time_sec: +e.target.value })}
                  />
                </div>
                <div>
                  <label className="section-heading block mb-1">Part. Size (MB)</label>
                  <input
                    type="number"
                    className="psg-btn-ghost w-full bg-white font-mono"
                    data-testid="mit-part-size"
                    value={form.partition_size_mb}
                    onChange={(e) => setForm({ ...form, partition_size_mb: +e.target.value })}
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2.5">
                <div>
                  <label className="section-heading block mb-1">Partition ID</label>
                  <input
                    type="number"
                    className="psg-btn-ghost w-full bg-white font-mono"
                    data-testid="mit-partition"
                    value={form.partition}
                    onChange={(e) => setForm({ ...form, partition: +e.target.value })}
                  />
                </div>
                <div>
                  <label className="section-heading block mb-1">Throttle % (if applicable)</label>
                  <input
                    type="number"
                    step="0.05"
                    className="psg-btn-ghost w-full bg-white font-mono"
                    data-testid="mit-throttle"
                    value={form.throttle_pct}
                    onChange={(e) => setForm({ ...form, throttle_pct: +e.target.value })}
                  />
                </div>
              </div>

              <div className="flex gap-2.5 pt-2">
                <button
                  className="psg-btn-primary flex-1 shadow-sm flex items-center justify-center gap-1.5"
                  onClick={() => decide()}
                  disabled={loadingDecide}
                  data-testid="mit-decide-btn"
                >
                  <span>{loadingDecide ? "Analyzing..." : "⚡ Analyze Buffer & Recommend"}</span>
                </button>
                <button
                  className="psg-btn-ghost px-4 bg-white hover:bg-[var(--psg-subpanel)] flex items-center gap-1"
                  onClick={run}
                  data-testid="mit-simulate-btn"
                >
                  <span>Simulate Action</span>
                </button>
              </div>

              {/* Dynamic Buffer Evaluation Card */}
              {decisionRes && (
                <div className="psg-subpanel p-3.5 mt-3 space-y-3 rounded-lg border border-[var(--psg-border)] bg-[var(--psg-subpanel)] shadow-sm">
                  {/* Top Bar: Action & Buffer Status Pill */}
                  <div className="flex items-center justify-between pb-2 border-b border-[var(--psg-border-soft)]">
                    <div>
                      <span className="section-heading block text-[10px]">Recommended Action</span>
                      <span className="text-base font-extrabold font-mono text-[var(--psg-primary)]">
                        {decisionRes.action}
                      </span>
                    </div>
                    <div>
                      <span
                        className={`psg-pill ${
                          decisionRes.buffer_status === "HEALTHY"
                            ? "pill-good"
                            : decisionRes.buffer_status === "TIGHT"
                            ? "pill-warn"
                            : "pill-crit"
                        }`}
                      >
                        Buffer: {decisionRes.buffer_status}
                      </span>
                    </div>
                  </div>

                  {/* Downgrade Banner if Exceeded */}
                  {decisionRes.downgraded && (
                    <div className="p-2.5 rounded-md bg-[#FFF4E5] border border-[#FFD599] text-[#7A4900] space-y-1">
                      <div className="flex items-center gap-1.5 font-bold text-xs text-[#C26D00]">
                        <span>⚠️ Buffer Deadline Exceeded — Graceful Downgrade</span>
                      </div>
                      <p className="text-[11px] leading-relaxed text-[#7A4900]">
                        {decisionRes.downgrade_reason}
                      </p>
                    </div>
                  )}

                  {/* 3 Metric Cards */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="bg-white p-2.5 rounded border border-[var(--psg-border-soft)] text-center">
                      <span className="kpi-label block text-[10px]">Lead Time</span>
                      <span className="font-mono font-bold text-xs text-[var(--psg-text)]">
                        {decisionRes.lead_time_sec}s
                      </span>
                    </div>
                    <div className="bg-white p-2.5 rounded border border-[var(--psg-border-soft)] text-center">
                      <span className="kpi-label block text-[10px]">Est. Duration</span>
                      <span className="font-mono font-bold text-xs text-[var(--psg-text)]">
                        {decisionRes.estimated_duration_sec}s
                      </span>
                    </div>
                    <div className="bg-white p-2.5 rounded border border-[var(--psg-border-soft)] text-center">
                      <span className="kpi-label block text-[10px]">Buffer Window</span>
                      <span
                        className={`font-mono font-bold text-xs ${
                          decisionRes.buffer_time_sec < 15 ? "text-[#B42318]" : "text-[#107E58]"
                        }`}
                      >
                        {decisionRes.buffer_time_sec > 0 ? `+${decisionRes.buffer_time_sec}` : decisionRes.buffer_time_sec}s
                      </span>
                    </div>
                  </div>

                  {/* Visual Buffer Bar */}
                  <div className="bg-white p-2.5 rounded border border-[var(--psg-border-soft)] space-y-1">
                    <div className="flex justify-between text-[10px] text-[var(--psg-text-2)] font-mono">
                      <span>Transfer ({decisionRes.estimated_duration_sec}s)</span>
                      <span>Buffer Window ({Math.max(0, decisionRes.buffer_time_sec)}s)</span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-[#E8EFF1] overflow-hidden flex">
                      <div
                        style={{
                          width: `${Math.min(100, Math.max(8, (decisionRes.estimated_duration_sec / Math.max(1, decisionRes.lead_time_sec)) * 100))}%`,
                        }}
                        className={`h-full ${decisionRes.downgraded ? "bg-[#B42318]" : "bg-[var(--psg-primary)]"}`}
                      ></div>
                      <div
                        style={{
                          width: `${Math.min(100, Math.max(0, (decisionRes.buffer_time_sec / Math.max(1, decisionRes.lead_time_sec)) * 100))}%`,
                        }}
                        className="h-full bg-[#107E58]/80"
                      ></div>
                    </div>
                  </div>

                  {/* Summary & Guardrail Details */}
                  <div className="space-y-1.5 text-xs text-[var(--psg-text-2)] pt-1">
                    <div className="leading-relaxed">
                      <b className="text-[var(--psg-text)]">Rationale:</b> {decisionRes.reason}
                    </div>
                    <div className="flex items-center justify-between text-[11px] pt-1 border-t border-[var(--psg-border-soft)]">
                      <span>Cost: <b>{decisionRes.cost}</b> · Benefit: <b>{decisionRes.benefit}</b></span>
                      <span>
                        Guardrail:{" "}
                        <b className={decisionRes.guardrail_passed ? "text-[#107E58]" : "text-[#B42318]"}>
                          {decisionRes.guardrail_passed ? "PASSED" : "BLOCKED"}
                        </b>
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </Section>
        </div>

        {/* Right Column: Recent Mitigations */}
        <div className="lg:col-span-2">
          <Section
            title="Recent Mitigations (Before / After & Buffer Telemetry)"
            right={<span className="text-xs text-[var(--psg-text-3)] font-mono">{mits.length} recorded</span>}
            testid="section-mit-log"
          >
            <div className="space-y-3 max-h-[580px] overflow-auto pr-1">
              {mits
                .slice()
                .reverse()
                .map((m) => (
                  <div key={m.id} className="psg-card p-3.5 bg-white border border-[var(--psg-border-soft)] shadow-sm hover:border-[var(--psg-primary)]/40 transition-colors">
                    {/* Item Header */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono font-bold text-sm text-[var(--psg-text)]">
                          {m.action}
                        </span>
                        <span className="font-mono text-xs text-[var(--psg-text-3)]">
                          #{m.id}
                        </span>
                        {m.buffer_telemetry?.downgraded && (
                          <span className="psg-pill pill-warn text-[10px]">
                            Downgraded from {m.buffer_telemetry.original_candidate || "MIGRATE"}
                          </span>
                        )}
                      </div>
                      <Pill tone="info">
                        {new Date(m.timestamp * 1000).toLocaleTimeString()}
                      </Pill>
                    </div>

                    {/* Buffer Context Chips */}
                    {m.buffer_telemetry?.lead_time_sec != null && (
                      <div className="flex flex-wrap gap-2 text-[11px] font-mono mb-2.5 pb-2 border-b border-[var(--psg-border-soft)]">
                        <span className="px-2 py-0.5 rounded bg-[var(--psg-subpanel)] border border-[var(--psg-border-soft)] text-[var(--psg-text-2)]">
                          Lead: <b>{m.buffer_telemetry.lead_time_sec}s</b>
                        </span>
                        <span className="px-2 py-0.5 rounded bg-[var(--psg-subpanel)] border border-[var(--psg-border-soft)] text-[var(--psg-text-2)]">
                          Est. Duration: <b>{m.buffer_telemetry.estimated_duration_sec ?? (m.action === "CACHE_PROMOTION" ? 1.0 : 12.0)}s</b>
                        </span>
                        <span className="px-2 py-0.5 rounded bg-[var(--psg-subpanel)] border border-[var(--psg-border-soft)] text-[var(--psg-text-2)]">
                          Buffer:{" "}
                          <b className={(m.buffer_telemetry.buffer_time_sec ?? 0) < 15 ? "text-[#B42318]" : "text-[#107E58]"}>
                            {m.buffer_telemetry.buffer_time_sec != null ? `${m.buffer_telemetry.buffer_time_sec}s` : "Safe"}
                          </b>
                        </span>
                        <span className={`psg-pill ${m.buffer_telemetry.buffer_status === "HEALTHY" ? "pill-good" : "pill-warn"}`}>
                          {m.buffer_telemetry.buffer_status || "OK"}
                        </span>
                      </div>
                    )}

                    {/* Before vs After Metric Cards */}
                    <div className="grid grid-cols-2 gap-3 font-mono text-xs">
                      {/* Before */}
                      <div className="bg-[var(--psg-subpanel)] p-2.5 rounded border border-[var(--psg-border-soft)]">
                        <span className="section-heading text-[10px] text-[var(--psg-text-3)] block mb-1">
                          Before Mitigation
                        </span>
                        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                          <div>P95: <b className="text-[var(--psg-text)]">{m.before.avg_p95.toFixed(1)}ms</b></div>
                          <div>P99: <b className="text-[var(--psg-text)]">{m.before.avg_p99.toFixed(1)}ms</b></div>
                          <div>Load CV: <b className="text-[var(--psg-text)]">{m.before.cluster_load_cv.toFixed(3)}</b></div>
                          <div>Queue: <b className="text-[var(--psg-text)]">{m.before.avg_queue.toFixed(1)}</b></div>
                        </div>
                      </div>

                      {/* After */}
                      <div className="bg-white p-2.5 rounded border border-[var(--psg-primary-subtle)]">
                        <span className="section-heading text-[10px] text-[var(--psg-primary)] block mb-1">
                          After Mitigation
                        </span>
                        <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                          <div>P95: <b className="text-[#107E58]">{m.after.avg_p95.toFixed(1)}ms</b></div>
                          <div>P99: <b className="text-[#107E58]">{m.after.avg_p99.toFixed(1)}ms</b></div>
                          <div>Load CV: <b className="text-[var(--psg-primary)]">{m.after.cluster_load_cv.toFixed(3)}</b></div>
                          <div>Queue: <b className="text-[#107E58]">{m.after.avg_queue.toFixed(1)}</b></div>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              {!mits.length && (
                <div className="text-sm text-[var(--psg-text-3)] p-8 text-center bg-white rounded-lg border border-[var(--psg-border-soft)]">
                  No mitigations executed yet. Select an action or use one of the Quick Test Scenarios to run a simulation.
                </div>
              )}
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}
