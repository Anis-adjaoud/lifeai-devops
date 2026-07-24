import { useEffect, useState } from 'react'

/**
 * Anneau de score circulaire (0–100, cercle complet = 100), animé.
 * La couleur est fournie par l'appelant (elle s'adapte au niveau/pourcentage).
 */
export default function ScoreRing({ score, color, size = 122 }) {
  const SW = 10
  const CX = size / 2
  const CY = size / 2
  const R = size / 2 - SW
  const CIRC = 2 * Math.PI * R

  const [anim, setAnim] = useState(0)
  useEffect(() => {
    const target = Math.max(0, Math.min(score ?? 0, 100)) / 100
    let start = null
    const step = (ts) => {
      if (!start) start = ts
      const p = Math.min((ts - start) / 900, 1)
      setAnim(target * (1 - Math.pow(1 - p, 3)))
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [score])

  const filled = CIRC * anim

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
      style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <filter id="score-ring-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="4" result="b" />
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
          filter="url(#score-ring-glow)"
          style={{ transition: 'stroke-dasharray 0.06s linear' }} />
      )}

      <text x={CX} y={CY + size * 0.02} textAnchor="middle" fill="#f1f5f9"
        fontSize={size * 0.30} fontWeight="800"
        fontFamily="-apple-system,'Inter',sans-serif">
        {score != null ? Math.round(score) : '—'}
      </text>
      <text x={CX} y={CY + size * 0.19} textAnchor="middle" fill="rgba(255,255,255,0.3)"
        fontSize={size * 0.10} fontFamily="-apple-system,'Inter',sans-serif">/100</text>
    </svg>
  )
}
