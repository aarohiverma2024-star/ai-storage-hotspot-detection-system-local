import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL}/api/v1`;
export const api = axios.create({ baseURL: API, timeout: 60000 });
export const j = async (fn) => { try { const r = await fn(); return r.data; } catch (e) { console.error(e); throw e; } };
export const endpoints = {
  health: () => api.get("/health"),
  cluster: () => api.get("/cluster"),
  telemetry: (limit=120) => api.get(`/telemetry?limit=${limit}`),
  hotspots: () => api.get("/hotspots"),
  predictions: (limit=50) => api.get(`/predictions?limit=${limit}`),
  explain: (nid) => api.get(`/explain/${nid}`),
  startWorkload: (body) => api.post("/workloads/start", body),
  stopWorkload: () => api.post("/workloads/stop"),
  resetWorkload: () => api.post("/workloads/reset"),
  presets: () => api.get("/workloads/presets"),
  ycsbValidate: () => api.get("/ycsb/validate"),
  trainModel: (body) => api.post("/models/train", body),
  listModels: () => api.get("/models"),
  activateModel: (name) => api.post(`/models/${name}/activate`),
  compareModels: () => api.get("/models/comparison"),
  decide: (body) => api.post("/decision", body),
  simulate: (body) => api.post("/mitigation/simulate", body),
  mitigations: () => api.get("/mitigations"),
  whatif: (body) => api.post("/whatif", body),
  runExperiments: (body) => api.post("/experiments/run", body),
  experiments: () => api.get("/experiments"),
  demoStart: () => api.post("/demo/start"),
  demoReset: () => api.post("/demo/reset"),
  audit: () => api.get("/audit"),
  ycsbRun: (body) => api.post("/ycsb/run", body),
  ycsbRuns: () => api.get("/ycsb/runs"),
  uploadCsv: (file) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/datasets/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
  },
  datasets: () => api.get("/datasets"),
};
