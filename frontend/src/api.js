const BASE = import.meta.env.VITE_API_URL ?? '';

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  getSources:              ()             => request('/api/sources'),
  toggleSource:            (id)           => request(`/api/sources/${id}/toggle`, { method: 'PUT' }),
  getSignals:              (params = {})  => request(`/api/signals?${new URLSearchParams(params)}`),
  getTopics:               (params = {})  => request(`/api/topics?${new URLSearchParams(params)}`),
  getTopicHistory:         (topic, weeks) => request(`/api/topics/history?topic=${encodeURIComponent(topic)}&weeks=${weeks}`),
  getTopicSignals:         (topic)        => request(`/api/topics/signals?topic=${encodeURIComponent(topic)}&limit=5`),
  getDemandSignals:        (params = {})  => request(`/api/demand-signals?${new URLSearchParams(params)}`),
  getDemandSignalDetail:   (label, params = {}) =>
    request(`/api/demand-signals/detail?label=${encodeURIComponent(label)}&${new URLSearchParams(params)}`),
  getDemandSignalLabels:   ()             => request('/api/demand-signals/labels'),
  mergeDemandSignals:      (source, target) =>
    request(`/api/demand-signals/merge?source_label=${encodeURIComponent(source)}&target_label=${encodeURIComponent(target)}`, { method: 'POST' }),
  triggerIngestion:        ()             => request('/api/ingest', { method: 'POST' }),
  getIngestionStatus:      ()             => request('/api/ingest/status'),
  triggerReenrich:         (limit = 200)  => request(`/api/enrich?limit=${limit}&workers=2`, { method: 'POST' }),
  getReenrichStatus:       ()             => request('/api/enrich/status'),
  getEnrichProviders:      ()             => request('/api/enrich/providers'),
};
