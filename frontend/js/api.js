/* Thin fetch wrapper shared by the customer catalog and staff dashboard. */
const API_BASE = ""; // same-origin: Flask serves the frontend + /api/*

function authToken() {
  return localStorage.getItem("sbg_staff_token") || "";
}

async function apiRequest(path, { method = "GET", body, auth = false, isCsv = false } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = authToken();
    if (token) headers["Authorization"] = "Bearer " + token;
  }
  const res = await fetch(API_BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && auth) {
    localStorage.removeItem("sbg_staff_token");
    localStorage.removeItem("sbg_staff_session");
    if (window.location.pathname.includes("staff") || window.location.pathname.includes("admin")) {
      window.location.reload();
    }
  }

  if (isCsv) {
    if (!res.ok) throw new Error("Export failed");
    return res.blob();
  }

  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }

  if (!res.ok) {
    const message = (data && data.error) || `Request failed (${res.status})`;
    throw new Error(message);
  }
  return data;
}

const api = {
  // public
  getMeta: () => apiRequest("/api/meta"),
  getGodowns: () => apiRequest("/api/godowns"),
  getSlabs: (params = {}) => {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v) qs.set(k, v); });
    const suffix = qs.toString() ? `?${qs}` : "";
    return apiRequest(`/api/slabs${suffix}`);
  },
  getSlab: (id) => apiRequest(`/api/slabs/${id}`),
  getAnnouncements: () => apiRequest("/api/announcements"),
  submitQuery: (payload) => apiRequest("/api/queries", { method: "POST", body: payload }),
  calcArea: (payload) => apiRequest("/api/calc/area", { method: "POST", body: payload }),

  // auth
  login: (username, password) => apiRequest("/api/auth/login", { method: "POST", body: { username, password } }),

  // staff
  createSlab: (payload) => apiRequest("/api/slabs", { method: "POST", body: payload, auth: true }),
  updateSlab: (id, payload) => apiRequest(`/api/slabs/${id}`, { method: "PUT", body: payload, auth: true }),
  deleteSlab: (id) => apiRequest(`/api/slabs/${id}`, { method: "DELETE", auth: true }),
  getTrash: () => apiRequest("/api/trash", { auth: true }),
  restoreTrash: (id) => apiRequest(`/api/trash/${id}/restore`, { method: "POST", auth: true }),
  purgeTrash: (id) => apiRequest(`/api/trash/${id}`, { method: "DELETE", auth: true }),
  getQueries: () => apiRequest("/api/queries", { auth: true }),
  updateQuery: (id, payload) => apiRequest(`/api/queries/${id}`, { method: "PUT", body: payload, auth: true }),
  getAllAnnouncements: () => apiRequest("/api/announcements/all", { auth: true }),
  createAnnouncement: (payload) => apiRequest("/api/announcements", { method: "POST", body: payload, auth: true }),
  updateAnnouncement: (id, payload) => apiRequest(`/api/announcements/${id}`, { method: "PUT", body: payload, auth: true }),
  deleteAnnouncement: (id) => apiRequest(`/api/announcements/${id}`, { method: "DELETE", auth: true }),
  getSummary: () => apiRequest("/api/reports/summary", { auth: true }),
  exportCsv: () => apiRequest("/api/reports/export.csv", { auth: true, isCsv: true }),
};
