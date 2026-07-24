import { useState } from 'react'

// Affiche le temps/tokens consommés, avec détail par agent
export default function UsagePanel({ usage }) {
  const [open, setOpen] = useState(false)
  if (!usage) return null

  const agents = Object.entries(usage.per_agent || {})

  return (
    <div style={{ marginTop: 10, fontSize: 11 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 8, padding: '5px 10px', color: 'var(--text-3)',
          cursor: 'pointer', fontSize: 11, display: 'flex', alignItems: 'center', gap: 6,
        }}
      >
        ⚡ {usage.elapsed_seconds?.toFixed(1)}s · {usage.total_tokens?.toLocaleString('fr-FR')} tokens
        · {usage.llm_calls} appel{usage.llm_calls > 1 ? 's' : ''} LLM
        <span style={{ opacity: 0.6 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && agents.length > 0 && (
        <div style={{
          marginTop: 6, background: 'rgba(255,255,255,0.03)',
          border: '1px solid rgba(255,255,255,0.07)', borderRadius: 10,
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
            <thead>
              <tr style={{ color: 'var(--text-3)', textAlign: 'left' }}>
                <th style={{ padding: '6px 10px', fontWeight: 600 }}>Agent</th>
                <th style={{ padding: '6px 10px', fontWeight: 600 }}>Appels</th>
                <th style={{ padding: '6px 10px', fontWeight: 600 }}>Tokens</th>
                <th style={{ padding: '6px 10px', fontWeight: 600 }}>Réflexion</th>
              </tr>
            </thead>
            <tbody>
              {agents.map(([name, a]) => (
                <tr key={name} style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                  <td style={{ padding: '6px 10px', color: 'var(--text-2)' }}>{name}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--text-2)' }}>{a.calls}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--text-2)' }}>{a.total.toLocaleString('fr-FR')}</td>
                  <td style={{ padding: '6px 10px', color: 'var(--text-2)' }}>{a.thoughts.toLocaleString('fr-FR')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
