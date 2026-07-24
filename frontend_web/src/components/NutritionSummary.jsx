const MACROS = [
  { key: 'carbs_g',   label: 'Glucides',  color: '#f59e0b', kcalPerG: 4 },
  { key: 'protein_g', label: 'Protéines', color: '#10b981', kcalPerG: 4 },
  { key: 'fat_g',     label: 'Lipides',   color: '#6366f1', kcalPerG: 9 },
]

function level(s) {
  if (s >= 80) return { label: 'Excellent', color: '#10b981' }
  if (s >= 65) return { label: 'Bon',       color: '#6366f1' }
  if (s >= 45) return { label: 'Attention', color: '#f59e0b' }
  return              { label: 'Critique',  color: '#ef4444' }
}

/**
 * Compte rendu nutrition du jour (ce que le user a déclaré) — SANS objectifs/limites,
 * c'est un simple bilan — suivi des résultats de l'analyse nutrition (score +
 * insights/recommandations du NutritionAgent), disponibles après une analyse.
 */
export default function NutritionSummary({ diary }) {
  if (!diary) return null

  const t = diary.totals || {}
  const hasData = (t.entries || 0) > 0
  const totalMacroKcal = MACROS.reduce((s, m) => s + (t[m.key] || 0) * m.kcalPerG, 0) || 1
  const mealsCount = Object.values(diary.meals || {}).filter(m => m.entries.length).length
  const analysis = diary.analysis
  const lv = analysis ? level(analysis.score) : null

  return (
    <div className="calorie-card nutri-report">
      {/* ── Compte rendu déclaré (factuel, aucun objectif) ── */}
      <div className="nr-declared">
        <div className="nr-cal">
          <span className="nr-cal-value">{Math.round(t.kcal || 0)}</span>
          <span className="nr-cal-unit">kcal consommées aujourd'hui</span>
        </div>
        <div className="nr-meta">
          <span>🍽 {mealsCount} repas</span>
          <span>💧 {diary.water_ml || 0} ml</span>
        </div>
      </div>

      <div className="macros-row">
        {MACROS.map(m => {
          const g = t[m.key] || 0
          const pct = Math.round((g * m.kcalPerG) / totalMacroKcal * 100)
          return (
            <div key={m.key} className="macro">
              <div className="macro-head">
                <span className="macro-label">{m.label}</span>
                <span className="macro-val">{Math.round(g)} g</span>
              </div>
              <div className="macro-bar">
                <div className="macro-bar-fill" style={{ width: `${pct}%`, background: m.color }} />
              </div>
            </div>
          )
        })}
      </div>

      {/* ── Résultats de l'analyse nutrition ── */}
      <div className="nr-divider" />

      {analysis ? (
        <div className="nr-analysis">
          <div className="nr-analysis-head">
            <div className="nr-analysis-title">Analyse nutrition</div>
            <span className="sc-badge" style={{ background: `${lv.color}1a`, color: lv.color }}>
              {lv.label} · {Math.round(analysis.score)}/100
            </span>
          </div>

          {analysis.anomalies?.length > 0 && (
            <div className="nr-list">
              {analysis.anomalies.map((a, i) => (
                <div key={i} className="nr-list-item nr-warn">⚠ {a}</div>
              ))}
            </div>
          )}
          {analysis.insights?.length > 0 && (
            <div className="nr-list">
              {analysis.insights.map((s, i) => (
                <div key={i} className="nr-list-item">• {s}</div>
              ))}
            </div>
          )}
          {analysis.recommendations?.length > 0 && (
            <div className="nr-list">
              {analysis.recommendations.map((r, i) => (
                <div key={i} className="nr-list-item nr-reco">→ {r}</div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="nr-analysis-empty">
          {hasData
            ? '📊 Lance une analyse pour évaluer ta nutrition à partir de ces données.'
            : 'Ajoute tes repas, puis lance une analyse pour obtenir ton bilan nutrition.'}
        </div>
      )}
    </div>
  )
}
