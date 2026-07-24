import { useState, useRef, useEffect, useCallback } from 'react'
import MarkdownMessage from '../components/MarkdownMessage.jsx'
import { NutriScoreBadge } from '../components/FoodSearch.jsx'
import UsagePanel from '../components/UsagePanel.jsx'
import { sendMessage, getConversations, getConvMessages, deleteConversation } from '../api/client.js'

const MEAL_LABELS = { breakfast: 'petit-déj', lunch: 'déjeuner', dinner: 'dîner', snack: 'collation' }

const SUGGESTIONS = [
  'Analyse mes données de santé',
  'Comment améliorer mon sommeil ?',
  'Quel est mon niveau de risque ?',
  'Donne-moi un plan cette semaine',
]

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
}

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 60_000)     return 'À l\'instant'
  if (diff < 3_600_000)  return `Il y a ${Math.floor(diff / 60_000)} min`
  if (diff < 86_400_000) return `Il y a ${Math.floor(diff / 3_600_000)} h`
  if (diff < 604_800_000) return d.toLocaleDateString('fr-FR', { weekday: 'short', day: 'numeric', month: 'short' })
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

const WELCOME = {
  role: 'agent',
  text: 'Bonjour ! Je suis **LifeAI**, votre coach santé IA propulsé par Gemini 2.5 Flash. Comment puis-je vous aider aujourd\'hui ?',
  ts: Date.now(),
}

export default function Chat({ userId }) {
  const [conversations, setConversations] = useState([])
  const [activeConv,    setActiveConv]    = useState(null)   // { id, title }
  const [messages,      setMessages]      = useState([WELCOME])
  const [input,         setInput]         = useState('')
  const [sessionId,     setSessionId]     = useState(null)
  const [loading,       setLoading]       = useState(false)
  const [showSugg,      setShowSugg]      = useState(true)
  const [sidebarOpen,   setSidebarOpen]   = useState(true)
  const [convLoading,   setConvLoading]   = useState(false)
  const bottomRef   = useRef(null)
  const textareaRef = useRef(null)

  // Charge la liste des conversations
  const loadConversations = useCallback(async () => {
    try {
      const list = await getConversations(userId)
      setConversations(list || [])
    } catch { /* silencieux */ }
  }, [userId])

  useEffect(() => { loadConversations() }, [loadConversations])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Ouvre une ancienne conversation et charge son historique
  const openConversation = async (conv) => {
    if (convLoading || activeConv?.id === conv.id) return
    setConvLoading(true)
    try {
      const msgs = await getConvMessages(conv.id)
      const mapped = (msgs || []).map(m => ({
        role: m.role === 'user' ? 'user' : 'agent',
        text: m.content,
        ts: new Date(m.created_at).getTime(),
      }))
      setActiveConv({ id: conv.id, title: conv.title })
      setMessages(mapped.length ? mapped : [WELCOME])
      setSessionId(null)   // sera recréé au prochain envoi
      setShowSugg(false)
    } catch (e) {
      // Signal visuel si l'ouverture d'une conversation échoue
      console.error('Erreur chargement conversation', e)
      setMessages([{
        role: 'agent', error: true,
        text: `❌ Impossible d'ouvrir cette conversation : ${e.message}`, ts: Date.now(),
      }])
    } finally {
      setConvLoading(false)
    }
  }

  // Nouvelle conversation vierge
  const startNewConversation = () => {
    setActiveConv(null)
    setSessionId(null)
    setMessages([WELCOME])
    setShowSugg(true)
    setInput('')
  }

  // Supprime une conversation
  const handleDelete = async (e, convId) => {
    e.stopPropagation()
    await deleteConversation(convId).catch(() => {})
    if (activeConv?.id === convId) startNewConversation()
    setConversations(prev => prev.filter(c => c.id !== convId))
  }

  const send = useCallback(async (text) => {
    const t = text.trim()
    if (!t || loading) return
    setShowSugg(false)
    setInput('')
    setMessages(m => [...m, { role: 'user', text: t, ts: Date.now() }])
    setLoading(true)
    textareaRef.current?.focus()

    try {
      const data = await sendMessage(userId, t, activeConv?.id || null)
      setSessionId(data.session_id)

      // Si c'était une nouvelle conv, met à jour l'état actif et recharge la liste
      if (!activeConv) {
        setActiveConv({ id: data.conversation_id, title: t.slice(0, 60) })
        await loadConversations()
      } else {
        // Met à jour le titre/date dans la liste locale
        setConversations(prev => prev.map(c =>
          c.id === data.conversation_id
            ? { ...c, updated_at: new Date().toISOString() }
            : c
        ))
      }
      setMessages(m => [...m, {
        role: 'agent',
        text: data.response || '(aucune réponse)',
        ts: Date.now(),
        loggedFoods: (data.logged_foods || []).filter(f => f.matched),
        usage: data.usage,
      }])
    } catch (e) {
      setMessages(m => [...m, {
        role: 'agent', error: true,
        text: `❌ Erreur : ${e.message}`, ts: Date.now(),
      }])
    } finally {
      setLoading(false)
    }
  }, [loading, activeConv, userId, loadConversations])

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) }
  }

  return (
    <div className="chat-root">
      {/* ── Sidebar conversations ─────────────────────────────────── */}
      <div className={`conv-sidebar ${sidebarOpen ? 'open' : 'closed'}`}>
        <div className="conv-sidebar-header">
          <span className="conv-sidebar-title">Conversations</span>
          <button className="icon-btn" onClick={() => setSidebarOpen(o => !o)} title="Réduire">
            {sidebarOpen ? '◀' : '▶'}
          </button>
        </div>

        <button className="new-conv-btn" onClick={startNewConversation}>
          <span>✏️</span> Nouvelle conversation
        </button>

        <div className="conv-list">
          {conversations.length === 0 && (
            <div className="conv-empty">Aucune conversation</div>
          )}
          {conversations.map(c => (
            <div
              key={c.id}
              className={`conv-item ${activeConv?.id === c.id ? 'active' : ''}`}
              onClick={() => openConversation(c)}
            >
              <div className="conv-item-content">
                <div className="conv-item-title">{c.title || 'Conversation'}</div>
                <div className="conv-item-date">{fmtDate(c.updated_at)}</div>
              </div>
              <button
                className="conv-delete-btn"
                onClick={(e) => handleDelete(e, c.id)}
                title="Supprimer"
              >×</button>
            </div>
          ))}
        </div>
      </div>

      {/* ── Zone de chat ──────────────────────────────────────────── */}
      <div className="chat-layout">
        <div className="chat-topbar">
          <div className="agent-info">
            {!sidebarOpen && (
              <button className="icon-btn" style={{ marginRight: 8 }}
                onClick={() => setSidebarOpen(true)} title="Ouvrir sidebar">☰</button>
            )}
            <div className="agent-avatar">🤖</div>
            <div>
              <div className="agent-name">
                {activeConv ? activeConv.title.slice(0, 50) : 'Chief Agent — LifeAI'}
              </div>
              <div className="agent-sub">
                <span className="online-badge">
                  <span style={{ width: 5, height: 5, background: '#10b981', borderRadius: '50%', display: 'inline-block' }} />
                  En ligne
                </span>
                {' '}· Gemini 2.5 Flash · Google ADK
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {activeConv && (
              <span style={{
                fontSize: 10, color: 'var(--text-3)',
                background: 'rgba(99,102,241,0.12)', border: '1px solid rgba(99,102,241,0.3)',
                padding: '3px 9px', borderRadius: 20,
              }}>
                Conv. active
              </span>
            )}
            <button className="action-btn" onClick={startNewConversation}>✏️ Nouveau</button>
          </div>
        </div>

        {/* Messages */}
        <div className="chat-messages">
          {convLoading && (
            <div style={{ textAlign: 'center', padding: 32, color: 'var(--text-3)' }}>
              Chargement de la conversation…
            </div>
          )}
          {!convLoading && messages.map((m, i) => (
            <div key={i} className={`msg-row ${m.role}${m.error ? ' error' : ''}`}>
              <div className="msg-avatar">{m.role === 'agent' ? '🤖' : '👤'}</div>
              <div>
                <div className="msg-bubble">
                  {m.role === 'agent' && !m.error
                    ? <MarkdownMessage text={m.text} />
                    : <span>{m.text}</span>
                  }
                </div>
                {m.loggedFoods?.length > 0 && (
                  <div className="food-logged">
                    <div className="food-logged-head">🍽 Ajouté à ton journal</div>
                    {m.loggedFoods.map((f, j) => (
                      <div key={j} className="food-logged-item">
                        <NutriScoreBadge grade={f.nutriscore} size={18} />
                        <span className="food-logged-name">{f.name}</span>
                        <span className="food-logged-meta">
                          {Math.round(f.quantity_g)} {f.is_liquid ? 'ml' : 'g'} · {f.kcal} kcal · {MEAL_LABELS[f.meal] || f.meal}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {m.role === 'agent' && <UsagePanel usage={m.usage} />}
                <div className="msg-time">{fmtTime(m.ts)}</div>
              </div>
            </div>
          ))}

          {loading && (
            <div className="msg-row agent">
              <div className="msg-avatar">🤖</div>
              <div className="msg-bubble">
                <div className="typing-wrap">
                  <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Suggestions */}
        {showSugg && (
          <div className="suggestions-row">
            {SUGGESTIONS.map(s => (
              <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
            ))}
          </div>
        )}

        {/* Input */}
        <div className="chat-input-area">
          <textarea
            ref={textareaRef}
            className="chat-textarea"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Posez votre question santé… (Entrée pour envoyer)"
            rows={2}
            disabled={loading}
          />
          <button
            className="send-btn"
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            title="Envoyer"
          >➤</button>
        </div>
      </div>
    </div>
  )
}
