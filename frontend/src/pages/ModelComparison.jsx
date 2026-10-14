import React, { useEffect, useState } from "react";
import { endpoints, j } from "../lib/api";
import { Section, Pill } from "../components/common/UI";
import { toast } from "sonner";

export default function ModelComparison() {
  const [data, setData] = useState(null);
  const [models, setModels] = useState([]);
  const load = async () => { setData(await j(() => endpoints.compareModels())); setModels((await j(() => endpoints.listModels())).models || []); };
  useEffect(() => { load(); }, []);
  const activate = async (name) => { await j(() => endpoints.activateModel(name)); toast.success(`Activated ${name}`); load(); };
  const rows = data?.models || [];
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-bold" data-testid="compare-title">Model Comparison</h1>
        <p className="text-sm text-[color:var(--psg-text-2)]">All measured on the held-out test split.</p></div>
      <Section title="Metrics Matrix" testid="section-compare-table">
        <div className="overflow-auto">
          <table className="w-full text-sm font-mono">
            <thead className="text-xs uppercase text-[color:var(--psg-text-2)]">
              <tr><th className="py-2 text-left">Model</th><th>Kind</th><th>Precision</th><th>Recall</th><th>F1</th><th>AUC</th><th>Infer (ms)</th><th>Trained (ms)</th><th /></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.name} className="border-t border-[color:var(--psg-border-soft)]">
                  <td className="py-2">{r.name}</td>
                  <td>{r.kind}</td>
                  <td>{r.precision}</td><td>{r.recall}</td><td>{r.f1}</td><td>{r.auc}</td>
                  <td>{r.inference_ms}</td><td>{r.elapsed_ms}</td>
                  <td><button className="psg-btn-ghost" onClick={() => activate(r.name)} data-testid={`compare-activate-${r.name}`}>Activate</button></td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={9} className="py-6 text-center text-[color:var(--psg-text-3)]">Train at least one model.</td></tr>}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  );
}
