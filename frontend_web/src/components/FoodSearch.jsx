import { useState, useEffect, useRef } from 'react'
import { searchFoods, addFoodLog } from '../api/client.js'

const NUTRISCORE_COLORS = {
  A: '#038141', B: '#85bb2f', C: '#fecb02', D: '#ee8100', E: '#e63e11',
}

const MEAL_LABELS = {
  breakfast: 'petit-déjeuner', lunch: 'déjeuner', dinner: 'dîner', snack: 'collations',
}

const QTY_PRESETS_SOLID  = [50, 100, 150, 200]
const QTY_PRESETS_LIQUID = [125, 200, 250, 330]

export function NutriScoreBadge({ grade, size = 22 }) {
  if (!grade) return null
  const g = String(grade).toUpperCase()
  return (
    <span className="nutriscore-badge" style={{
      background: NUTRISCORE_COLORS[g] || '#64748b',
      width: size, height: size, fontSize: size * 0.55,
    }}>{g}</span>
  )
}

export default function FoodSearch({ userId, meal, onClose, onAdded }) {
  const [query,    setQuery]    = useState('')
  const [results,  setResults]  = useState([])
  const [loading,  setLoading]  = useState(false)
  const [selected, setSelected] = useState(null)   // aliment choisi
  const [qty,      setQty]      = useState(100)
  const [saving,   setSaving]   = useState(false)
  const [error,    setError]    = useState('')
  const inputRef = useRef(null)
  const timer = useRef(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  // Recherche avec debounce
  useEffect(() => {
    if (selected) return
    const q = query.trim()
    if (q.length < 2) { setResults([]); return }
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      setLoading(true)
      searchFoods(q)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setLoading(false))
    }, 250)
    return () => clearTimeout(timer.current)
  }, [query, selected])

  const kcalPreview = selected
    ? Math.round((selected.kcal_100g || 0) * qty / 100)
    : 0

  const handleAdd = async () => {
    setSaving(true); setError('')
    try {
      const diary = await addFoodLog(userId, {
        meal, food_code: selected.code, quantity_g: Number(qty),
      })
      onAdded(diary)
      onClose()
    } catch (e) {
      setError(e.message); setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">
            {selected ? 'Quelle quantité ?' : `Ajouter à ${MEAL_LABELS[meal] || meal}`}
          </div>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        {error && <div className="error-banner">⚠ {error}</div>}

        {!selected ? (
          <>
            <input ref={inputRef} className="food-search-input" type="text"
              placeholder="Rechercher un aliment (ex. pomme, poulet…)"
              value={query} onChange={e => setQuery(e.target.value)} />

            <div className="food-results">
              {loading && <div className="food-hint">Recherche…</div>}
              {!loading && query.trim().length >= 2 && results.length === 0 && (
                <div className="food-hint">Aucun aliment trouvé</div>
              )}
              {!loading && query.trim().length < 2 && (
                <div className="food-hint">Tape au moins 2 lettres</div>
              )}
              {results.map(f => (
                <button key={f.code} className="food-row" onClick={() => setSelected(f)}>
                  <NutriScoreBadge grade={f.nutriscore} />
                  <div className="food-row-main">
                    <div className="food-row-name">{f.name}</div>
                    <div className="food-row-sub">
                      {Math.round(f.kcal_100g || 0)} kcal / 100 {f.is_liquid ? 'ml' : 'g'}
                      {f.category ? ` · ${f.category}` : ''}
                    </div>
                  </div>
                  <span className="food-row-add">+</span>
                </button>
              ))}
            </div>
          </>
        ) : (
          <div className="portion-panel">
            <div className="portion-food">
              <NutriScoreBadge grade={selected.nutriscore} size={26} />
              <div>
                <div className="food-row-name">{selected.name}</div>
                <div className="food-row-sub">{Math.round(selected.kcal_100g || 0)} kcal / 100 {selected.is_liquid ? 'ml' : 'g'}</div>
              </div>
            </div>

            <label className="form-label" style={{ marginTop: 4 }}>
              Quantité ({selected.is_liquid ? 'millilitres' : 'grammes'})
            </label>
            <input className="form-input" type="number" min="1" max="2000"
              value={qty} onChange={e => setQty(e.target.value)} />
            <div className="portion-presets">
              {(selected.is_liquid ? QTY_PRESETS_LIQUID : QTY_PRESETS_SOLID).map(p => (
                <button key={p}
                  className={`portion-preset${Number(qty) === p ? ' active' : ''}`}
                  onClick={() => setQty(p)}>{p} {selected.is_liquid ? 'ml' : 'g'}</button>
              ))}
            </div>

            <div className="portion-preview">
              <span>Apport</span>
              <strong>{kcalPreview} kcal</strong>
            </div>

            <div className="portion-actions">
              <button className="action-btn" onClick={() => setSelected(null)}>← Retour</button>
              <button className={`analyze-btn${saving ? ' running' : ''}`}
                onClick={handleAdd} disabled={saving || Number(qty) <= 0}>
                {saving ? <><span className="spinner">⟳</span> Ajout…</> : <>Ajouter</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
