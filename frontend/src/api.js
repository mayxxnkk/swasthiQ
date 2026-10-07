const BASE = import.meta.env.VITE_API_URL || ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `POST ${path} → ${res.status}`)
  }
  return res.json()
}

export const api = {
  listConversations: () => get('/conversations'),
  getConversation:  (id) => get(`/conversations/${id}`),
  runConversation:  (payload) => post('/agent/run', payload),
  health:           () => get('/health'),
}
