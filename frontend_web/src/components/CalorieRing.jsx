import { useEffect, useState } from 'react'

const R = 82, CX = 100, CY = 100, SW = 14
const CIRC = 2 * Math.PI * R

/**
 * Anneau de calories façon YAZIO.
 * restant = objectif − mangé + sport (calories brûlées Google Fit).
 */
export default function CalorieRing({ eaten = 0, goal = 2000, exercise = 0 }) {
  const budget = goal + exercise
  const remaining = Math.round(budget - eaten)
  const pct = budget > 0 ? Math.min(eaten / budget, 1) : 0
  const over = eaten > budget
  const color = over ? '#ef4444' : eaten / budget > 0.85 ? '#f59e0b' : '#10b981'

  const [anim, setAnim] = useState(0)
  useEffect(() => {
    let start = null
    const target = pct
    const step = (ts) => {
      if (!start) start = ts
      const p = Math.min((ts - start) / 900, 1)
      setAnim(target * (1 - Math.pow(1 - p, 3)))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [pct])

  const filled = CIRC * anim

  return (
    <svg width="200" height="200" viewBox="0 0 200 200" style={{ overflow: 'visible' }}>
      <defs>
        <filter id="ring-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="5" result="b" />
          <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      <circle cx={CX} cy={CY} r={R} fill="none"
        stroke="rgba(255,255,255,0.07)" strokeWidth={SW} />

      {anim > 0.001 && (
        <circle cx={CX} cy={CY} r={R} fill="none"
          stroke={color} strokeWidth={SW} strokeLinecap="round"
          strokeDasharray={`${filled} ${CIRC - filled}`}
          transform={`rotate(-90 ${CX} ${CY})`}
          filter="url(#ring-glow)"
          style={{ transition: 'stroke-dasharray 0.06s linear' }} />
      )}

      <text x={CX} y={CY - 2} textAnchor="middle" fill="#f1f5f9"
        fontSize="42" fontWeight="800" fontFamily="-apple-system,'Inter',sans-serif">
        {Math.abs(remaining)}
      </text>
      <text x={CX} y={CY + 22} textAnchor="middle" fill="rgba(255,255,255,0.4)"
        fontSize="12" fontFamily="-apple-system,'Inter',sans-serif">
        {over ? 'kcal en trop' : 'kcal restantes'}
      </text>
    </svg>
  )
}
