const BASE = "/api";

async function req(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  stats: () => req("/stats"),
  incidents: (status) => req(`/incidents${status ? `?status=${status}` : ""}`),
  incident: (id) => req(`/incidents/${id}`),
  incidentEvents: (id) => req(`/incidents/${id}/events`),
  acknowledge: (id) => req(`/incidents/${id}/acknowledge`, { method: "POST" }),
  assignCrew: (id, crew_name) =>
    req(`/incidents/${id}/assign-crew`, { method: "POST", body: JSON.stringify({ crew_name }) }),
  resolve: (id) => req(`/incidents/${id}/resolve`, { method: "POST" }),
  close: (id) => req(`/incidents/${id}/close`, { method: "POST" }),
  poles: (dtId) => req(`/poles${dtId ? `?dt_id=${dtId}` : ""}`),
  topology: (dtId) => req(`/topology/${dtId}`),

  simFault: (payload) => req(`/simulator/fault`, { method: "POST", body: JSON.stringify(payload) }),
  simRepair: (incident_id) => req(`/simulator/repair`, { method: "POST", body: JSON.stringify({ incident_id }) }),
  simStorm: (count) => req(`/simulator/storm`, { method: "POST", body: JSON.stringify({ count }) }),
  simStatus: () => req(`/simulator/status`),
  scheduledOutages: () => req(`/simulator/scheduled-outages`),
  createScheduledOutage: (payload) =>
    req(`/simulator/scheduled-outages`, { method: "POST", body: JSON.stringify(payload) }),
};
