const API = "";

async function request(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const text = await res.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail || res.status));
  }
  return data;
}

export const api = {
  listProjects: () => request("/api/projects"),
  createProject: (body) => request("/api/projects", { method: "POST", body: JSON.stringify(body) }),
  updateProject: (id, body) =>
    request(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (id) => request(`/api/projects/${id}`, { method: "DELETE" }),
  getMemories: (id) => request(`/api/projects/${id}/memories`),
  addMemory: (id, body) =>
    request(`/api/projects/${id}/memories`, { method: "POST", body: JSON.stringify(body) }),
  getMessages: (id) => request(`/api/projects/${id}/messages`),
  chat: (id, body) => request(`/api/projects/${id}/chat`, { method: "POST", body: JSON.stringify(body) }),
  approve: (pid, cid) =>
    request(`/api/projects/${pid}/creatives/${cid}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: "" }),
    }),
  getSettings: () => request("/api/settings"),
  saveSettings: (body) => request("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  getMetrics: (projectId) =>
    request(projectId ? `/api/metrics?project_id=${projectId}` : "/api/metrics"),
};

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
