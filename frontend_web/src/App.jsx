import React, { useState, useEffect, useCallback } from 'react'
import Dashboard      from './pages/Dashboard.jsx'
import Chat           from './pages/Chat.jsx'
import NutritionDiary from './pages/NutritionDiary.jsx'
import LoginPage      from './pages/LoginPage.jsx'
import { getUsers, getMe, logout } from './api/client.js'
import { useGoogleFitConnect } from './hooks/useGoogleFitConnect'

class ErrorBoundary extends React.Component {
  state = { error: null }
  static getDerivedStateFromError(e) { return { error: e } }
  componentDidCatch(error, info) { console.error('[LifeAI] render crash:', error, info) }
  render() {
    if (this.state.error) {
      return (
        <div style={{
          padding: '40px 32px', color: '#f1f5f9', fontFamily: 'monospace',
          display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: '#ef4444' }}>
            ⚠ Erreur de rendu
          </div>
          <div style={{ fontSize: 13, color: '#94a3b8', background: 'rgba(239,68,68,0.08)',
            border: '1px solid rgba(239,68,68,0.2)', borderRadius: 10, padding: '12px 16px' }}>
            {this.state.error.message}
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ width: 'fit-content', padding: '8px 20px', borderRadius: 8, border: 'none',
              background: 'rgba(124,58,237,0.3)', color: '#f1f5f9', cursor: 'pointer', fontSize: 13 }}
          >
            Réessayer
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function ConnectAccountButton({ onConnected }) {
  const { status, connect } = useGoogleFitConnect(onConnected)
  return (
    <button
      className="nav-item"
      onClick={connect}
      disabled={status === 'waiting'}
      style={{ marginTop: 8, cursor: status === 'waiting' ? 'not-allowed' : 'pointer', opacity: status === 'waiting' ? 0.6 : 1 }}
    >
      <span className="nav-icon">➕</span>
      {status === 'waiting' ? 'Connexion…' : 'Connecter un compte'}
    </button>
  )
}

function LogoutButton({ onLoggedOut }) {
  const [loading, setLoading] = useState(false)
  const [failed,  setFailed]  = useState(false)
  const handleClick = () => {
    setLoading(true)
    setFailed(false)
    // Vide l'état client seulement après confirmation du serveur
    logout()
      .then(() => onLoggedOut())
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }
  return (
    <button
      className="nav-item"
      onClick={handleClick}
      disabled={loading}
      title={failed ? 'La déconnexion a échoué, réessaie.' : undefined}
      style={{ marginTop: 8, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.6 : 1 }}
    >
      <span className="nav-icon">{failed ? '⚠️' : '🚪'}</span>
      {loading ? 'Déconnexion…' : failed ? 'Échec — réessayer' : 'Déconnexion'}
    </button>
  )
}

const TABS = [
  { id:'dashboard', label:'Dashboard',  icon:'📊' },
  { id:'nutrition', label:'Nutrition',  icon:'🥗' },
  { id:'chat',      label:'Chat IA',    icon:'💬' },
]

export default function App() {
  const [tab,    setTab]    = useState('dashboard')
  const [me,     setMe]     = useState(undefined) // undefined=chargement, null=anonyme, {..}=connecté
  const [users,  setUsers]  = useState([])
  const [userId, setUserId] = useState('')

  const loadMe = useCallback(() => {
    getMe().then(setMe).catch(() => setMe(null))
  }, [])

  const loadUsers = useCallback((selectId) => {
    getUsers()
      .then(data => {
        const list = Array.isArray(data) ? data : []
        setUsers(list)
        setUserId(prev => selectId || prev || (list.length ? list[0].user_id : ''))
      })
      .catch(() => {})
  }, [])

  useEffect(() => { loadMe() }, [loadMe])

  // La liste /api/users dépend du rôle, propre compte en premier
  useEffect(() => {
    if (me === undefined) return
    loadUsers(me ? me.user_id : undefined)
  }, [me, loadUsers])

  const handleLoggedOut = useCallback(() => {
    setUserId('')
    setUsers([])
    loadMe()
  }, [loadMe])

  const handleConnected = useCallback((uid) => {
    loadMe()
    loadUsers(uid)
  }, [loadMe, loadUsers])

  const topbarInfo = {
    dashboard: { title: 'Dashboard santé', sub: 'Vue d\'ensemble de vos indicateurs' },
    nutrition: { title: 'Journal alimentaire', sub: 'Suivez vos repas, calories et macros' },
    chat:      { title: 'Chat IA',         sub: 'Conversation avec votre coach LifeAI' },
  }

  if (me === undefined) {
    return (
      <div className="layout" style={{ alignItems:'center', justifyContent:'center', color:'var(--text-3)' }}>
        Chargement…
      </div>
    )
  }

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-icon">🏥</div>
          <div>
            <div className="brand-name">LifeAI</div>
            <div className="brand-sub">Health Intelligence</div>
          </div>
        </div>

        <div className="nav-section-label">Navigation</div>
        <nav className="sidebar-nav">
          {TABS.map(t => (
            <button
              key={t.id}
              className={`nav-item${tab === t.id ? ' active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span className="nav-icon">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="user-label">Utilisateur actif</div>
          <select
            className="user-select-dark"
            value={userId}
            onChange={e => setUserId(e.target.value)}
          >
            {users.length === 0 && (
              <option value="">Aucun utilisateur</option>
            )}
            {users.map(u => (
              <option key={u.user_id} value={u.user_id}>
                {u.name || u.user_id}
              </option>
            ))}
          </select>
          <ConnectAccountButton onConnected={handleConnected} />
          {me && <LogoutButton onLoggedOut={handleLoggedOut} />}
        </div>
      </aside>

      {/* Main */}
      <div className="main-area">
        <div className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">{topbarInfo[tab].title}</div>
            <div className="topbar-sub">{topbarInfo[tab].sub}</div>
          </div>
          <div className="live-badge">
            <div className="pulse-dot" />
            {userId || 'Aucun utilisateur'}
          </div>
        </div>

        <ErrorBoundary>
          {!userId
            ? <LoginPage onConnected={handleConnected} />
            : tab === 'dashboard'
              ? <Dashboard      userId={userId} key={userId}
                                onGoToNutrition={() => setTab('nutrition')} />
              : tab === 'nutrition'
                ? <NutritionDiary userId={userId} key={`nutri-${userId}`} />
                : <Chat           userId={userId} key={`chat-${userId}`} />
          }
        </ErrorBoundary>
      </div>
    </div>
  )
}
