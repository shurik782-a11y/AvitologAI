const API = "";

function telegramInitData() {
  try {
    return window.Telegram?.WebApp?.initData || "";
  } catch {
    return "";
  }
}

async function request(path, options = {}) {
  const initData = telegramInitData();
  const res = await fetch(`${API}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
      ...(options.headers || {}),
    },
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
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail || res.status));
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  authMe: () => request("/api/auth/me"),
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
      body: JSON.stringify({ note: "", trigger_upload: true }),
    }),
  getSettings: () => request("/api/settings"),
  saveSettings: (body) => request("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  getMetrics: (projectId) =>
    request(projectId ? `/api/metrics?project_id=${projectId}` : "/api/metrics"),
  billing: () => request("/api/billing/summary"),
  publications: (id) => request(`/api/projects/${id}/publications`),
  publishRuns: (id) => request(`/api/projects/${id}/publish-runs`),
  triggerPublish: (id) => request(`/api/projects/${id}/publish`, { method: "POST", body: "{}" }),
  metricPublications: (id) => request(`/api/projects/${id}/metrics/publications`),
  metricSnapshot: (pid, cid) => request(`/api/projects/${pid}/metrics/publications/${cid}`),
  metricRefresh: (pid, cid) =>
    request(`/api/projects/${pid}/metrics/publications/${cid}/refresh`, { method: "POST", body: "{}" }),
  patchCreative: (pid, cid, body) =>
    request(`/api/projects/${pid}/creatives/${cid}`, { method: "PATCH", body: JSON.stringify(body) }),
};

export async function apiUpload(path, formData) {
  const initData = telegramInitData();
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: {
      ...(initData ? { "X-Telegram-Init-Data": initData } : {}),
    },
    body: formData,
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

export function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
