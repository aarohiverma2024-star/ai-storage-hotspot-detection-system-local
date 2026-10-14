import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import AppShell from "./components/layout/AppShell";
import Overview from "./pages/Overview";
import LiveCluster from "./pages/LiveCluster";
import HotspotMonitor from "./pages/HotspotMonitor";
import Explainability from "./pages/Explainability";
import MitigationCenter from "./pages/MitigationCenter";
import WorkloadLab from "./pages/WorkloadLab";
import ModelTraining from "./pages/ModelTraining";
import ModelComparison from "./pages/ModelComparison";
import Experiments from "./pages/Experiments";
import WhatIf from "./pages/WhatIf";
import SystemHealth from "./pages/SystemHealth";
import Demo from "./pages/Demo";
import "./App.css";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell>
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/cluster" element={<LiveCluster />} />
          <Route path="/hotspots" element={<HotspotMonitor />} />
          <Route path="/explain" element={<Explainability />} />
          <Route path="/mitigation" element={<MitigationCenter />} />
          <Route path="/workloads" element={<WorkloadLab />} />
          <Route path="/training" element={<ModelTraining />} />
          <Route path="/compare" element={<ModelComparison />} />
          <Route path="/experiments" element={<Experiments />} />
          <Route path="/whatif" element={<WhatIf />} />
          <Route path="/health" element={<SystemHealth />} />
          <Route path="/demo" element={<Demo />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
