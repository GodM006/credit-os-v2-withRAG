const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function handle(res) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  generateCase: (scenario) =>
    fetch(`${API_BASE}/api/layer1/cases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    }).then(handle),

  generateLinkedPair: (scenario) =>
    fetch(`${API_BASE}/api/layer1/cases/linked-pair`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario }),
    }).then(handle),

  runCase: (caseId) =>
    fetch(`${API_BASE}/api/layer1/cases/${caseId}/run`, { method: "POST" }).then(handle),

  getCase: (caseId) => fetch(`${API_BASE}/api/layer1/cases/${caseId}`).then(handle),

  listCases: () => fetch(`${API_BASE}/api/layer1/cases`).then(handle),

  runLayer2: (caseId) =>
    fetch(`${API_BASE}/api/layer2/cases/${caseId}/run`, { method: "POST" }).then(handle),

  runLayer3: (caseId) =>
    fetch(`${API_BASE}/api/layer3/cases/${caseId}/run`, { method: "POST" }).then(handle),

  runLayer4: (caseId) =>
    fetch(`${API_BASE}/api/layer4/cases/${caseId}/run`, { method: "POST" }).then(handle),

  runLayer5: (caseId) =>
    fetch(`${API_BASE}/api/layer5/cases/${caseId}/run`, { method: "POST" }).then(handle),

  getModelInfo: () =>
    fetch(`${API_BASE}/api/layer5/model-info`).then(handle),

  runLayer6: (caseId) =>
    fetch(`${API_BASE}/api/layer6/cases/${caseId}/run`, { method: "POST" }).then(handle),

  getMemo: (caseId) =>
    fetch(`${API_BASE}/api/layer6/cases/${caseId}/memo`).then(handle),

  getCaseGraph: (caseId) => fetch(`${API_BASE}/api/layer2/cases/${caseId}/graph`).then(handle),

  getRelatedParties: (caseId) =>
    fetch(`${API_BASE}/api/layer2/cases/${caseId}/related-parties`).then(handle),
};
