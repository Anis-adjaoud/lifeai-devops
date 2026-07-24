const BASE = '/api'

async function req(url, opts = {}) {
  const r = await fetch(BASE + url, opts)
  if (!r.ok) {
    const err = await r.json().catch(() => ({}))
    throw new Error(err.detail || `HTTP ${r.status}`)
  }
  return r.json()
}

export const getMe       = ()           => req('/me')
export const logout      = ()           => fetch('/auth/logout', { method: 'POST' }).then(r => r.json())
export const getUsers    = ()           => req('/users')
export const getProfile  = (uid)        => req(`/profile/${uid}`)
export const getSessions = (uid, days=30) => req(`/sessions/${uid}?days=${days}`)
export const getPatterns = (uid)        => req(`/patterns/${uid}`)
export const getNotes    = (uid)        => req(`/notes/${uid}`)
export const getTrend    = (uid, days=7)=> req(`/trend/${uid}?days=${days}`)
export const getMetrics  = (uid, days=30) => req(`/metrics/${uid}?days=${days}`)

export const runAnalysis = (uid) =>
  req(`/analyze/${uid}`, { method: 'POST' })

// ── Nutrition (journal alimentaire façon YAZIO) ─────────────────────────────────
export const searchFoods = (q) => req(`/foods/search?q=${encodeURIComponent(q)}`)
export const getDiary = (uid) => req(`/nutrition/${uid}/diary`)
export const addFoodLog = (uid, payload) =>
  req(`/nutrition/${uid}/log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
export const deleteFoodLog = (id) =>
  req(`/nutrition/log/${id}`, { method: 'DELETE' })
export const setWater = (uid, ml) =>
  req(`/nutrition/${uid}/water`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ml }),
  })
export const setGoal = (uid, kcal_goal) =>
  req(`/nutrition/${uid}/goal`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kcal_goal }),
  })

export const sendMessage = (uid, message, conversationId = null) =>
  req(`/chat/${uid}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, conversation_id: conversationId }),
  })

export const resetSession = (sid) =>
  fetch(`${BASE}/chat/session/${sid}`, { method: 'DELETE' })

// ── Conversations ──────────────────────────────────────────────────────────────
export const getConversations = (uid)     => req(`/conversations/${uid}`)
export const getConvMessages  = (convId)  => req(`/conversations/${convId}/messages`)
export const deleteConversation = (convId) =>
  req(`/conversations/${convId}`, { method: 'DELETE' })
