import { useState, useEffect, useCallback } from 'react'
import FoodSearch, { NutriScoreBadge } from '../components/FoodSearch.jsx'
import { getDiary, deleteFoodLog, setWater } from '../api/client.js'

const MEALS = [
  { id: 'breakfast', label: 'Petit-déjeuner', icon: '🌅' },
  { id: 'lunch',     label: 'Déjeuner',       icon: '☀️' },
  { id: 'dinner',    label: 'Dîner',          icon: '🌙' },
  { id: 'snack',     label: 'Collations',     icon: '🍎' },
]

const WATER_GOAL = 2000
const GLASS = 250

export default function NutritionDiary({ userId }) {
  const [diary,       setDiary]       = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [loadError,   setLoadError]   = useState(null)
  const [actionError, setActionError] = useState(null)
  const [search,       setSearch]      = useState(null)   // repas dont la modale est ouverte

  const reload = useCallback(() => {
    return getDiary(userId).then(d => { setDiary(d); setLoadError(null) })
      .catch(() => setLoadError("Impossible de charger le journal alimentaire."))
  }, [userId])

  useEffect(() => { setLoading(true); reload().finally(() => setLoading(false)) }, [reload])

  const handleDelete = async (id) => {
    try {
      await deleteFoodLog(id)
      setActionError(null)
      reload()
    } catch {
      setActionError("La suppression a échoué, réessaie.")
    }
  }

  const handleWater = async (delta) => {
    try {
      const next = Math.max(0, (diary.water_ml || 0) + delta)
      await setWater(userId, next)
      setActionError(null)
      reload()
    } catch {
      setActionError("La mise à jour de l'hydratation a échoué, réessaie.")
    }
  }

  if (loading) return (
    <div className="page">
      <div className="nutri-diary">
        {[0, 1, 2].map(i => (
          <div key={i} className="card card-p" style={{ height: 90 }}>
            <div className="skeleton" style={{ height: 14, width: '30%', marginBottom: 12 }} />
            <div className="skeleton" style={{ height: 34, width: '100%' }} />
          </div>
        ))}
      </div>
    </div>
  )

  if (loadError || !diary) return (
    <div className="page">
      <div className="card card-p" style={{ textAlign: 'center', padding: 32 }}>
        <p style={{ color: '#f87171', marginBottom: 16 }}>
          {loadError || "Impossible de charger le journal alimentaire."}
        </p>
        <button className="meal-add" onClick={() => { setLoading(true); reload().finally(() => setLoading(false)) }}>
          Réessayer
        </button>
      </div>
    </div>
  )

  const glasses = Math.round((diary.water_ml || 0) / GLASS)

  return (
    <div className="page">
      {actionError && (
        <div className="card card-p" style={{ marginBottom: 12, color: '#f87171' }}>
          {actionError}
        </div>
      )}
      <div className="nutri-diary">

        {/* ── Sections repas ── */}
        {MEALS.map(meal => {
          const m = diary.meals[meal.id] || { entries: [], kcal: 0 }
          return (
            <div key={meal.id} className="meal-card">
              <div className="meal-head">
                <div className="meal-title">
                  <span className="meal-icon">{meal.icon}</span>
                  {meal.label}
                </div>
                <span className="meal-kcal">{m.kcal} kcal</span>
              </div>

              {m.entries.length > 0 && (
                <div className="meal-entries">
                  {m.entries.map(e => (
                    <div key={e.id} className="meal-entry">
                      <NutriScoreBadge grade={e.nutriscore} size={20} />
                      <div className="meal-entry-main">
                        <div className="meal-entry-name">{e.name || e.food_code}</div>
                        <div className="meal-entry-sub">{Math.round(e.quantity_g)} {e.is_liquid ? 'ml' : 'g'}</div>
                      </div>
                      <span className="meal-entry-kcal">{Math.round(e.kcal)} kcal</span>
                      <button className="meal-entry-del" onClick={() => handleDelete(e.id)}>×</button>
                    </div>
                  ))}
                </div>
              )}

              <button className="meal-add" onClick={() => setSearch(meal.id)}>
                + Ajouter un aliment
              </button>
            </div>
          )
        })}

        {/* ── Eau ── */}
        <div className="water-card">
          <div className="water-head">
            <div className="meal-title"><span className="meal-icon">💧</span> Hydratation</div>
            <span className="meal-kcal">{diary.water_ml || 0} / {WATER_GOAL} ml</span>
          </div>
          <div className="water-body">
            <button className="water-btn" onClick={() => handleWater(-GLASS)}>−</button>
            <div className="water-glasses">
              {Array.from({ length: Math.max(8, glasses) }).map((_, i) => (
                <span key={i} className={`water-glass${i < glasses ? ' filled' : ''}`}>🥛</span>
              ))}
            </div>
            <button className="water-btn" onClick={() => handleWater(GLASS)}>+</button>
          </div>
          <div className="water-sub">{glasses} verre{glasses > 1 ? 's' : ''} · 1 verre = 250 ml</div>
        </div>
      </div>

      {search && (
        <FoodSearch userId={userId} meal={search}
          onClose={() => setSearch(null)}
          onAdded={(d) => setDiary(d)} />
      )}
    </div>
  )
}
