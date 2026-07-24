import { useEffect, useState } from 'react'

const R = 78
const CX = 100, CY = 98
const CIRC = 2 * Math.PI * R
const ARC_DEG = 240
const ARC = CIRC * (ARC_DEG / 360)
const ROT = 150  // rotate so gap sits at bottom

const LEVEL_COLOR = {
  Excellent: '#10b981',
  Bon:       '#6366f1',
  Attention: '#f59e0b',
  Critique:  '#ef4444',
}

function getLevel(s) {
  if (s >= 80) return 'Excellent'
  if (s >= 65) return 'Bon'
  if (s >= 45) return 'Attention'
  return 'Critique'
}

export default function RadialGauge({ score }) {
  const [anim, setAnim] = useState(0)

  useEffect(() => {
    if (score == null) return
    let start = null
    const target = score
    const step = (ts) => {
      if (!start) start = ts
      const p = Math.min((ts - start) / 1100, 1)
      const eased = 1 - Math.pow(1 - p, 3)
      setAnim(target * eased)
      if (p < 1) requestAnimationFrame(step)
    }
    requestAnimationFrame(step)
  }, [score])

  const s = anim
  const level = getLevel(score ?? 0)
  const color = LEVEL_COLOR[level]
  const filled = ARC * (s / 100)

  return (
    <svg width="200" height="185" viewBox="0 0 200 185" style={{ overflow: 'visible' }}>
      <defs>
        <filter id="glow-soft" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      {/* Background track */}
      <circle cx={CX} cy={CY} r={R}
        fill="none" stroke="rgba(255,255,255,0.07)" strokeWidth="11"
        strokeDasharray={`${ARC} ${CIRC - ARC}`} strokeLinecap="round"
        transform={`rotate(${ROT} ${CX} ${CY})`}
      />

      {/* Glow halo */}
      {s > 1 && (
        <circle cx={CX} cy={CY} r={R}
          fill="none" stroke={color} strokeWidth="11" opacity="0.25"
          strokeDasharray={`${filled} ${CIRC - filled}`} strokeLinecap="round"
          transform={`rotate(${ROT} ${CX} ${CY})`}
          filter="url(#glow-soft)"
        />
      )}

      {/* Score arc */}
      {s > 1 && (
        <circle cx={CX} cy={CY} r={R}
          fill="none" stroke={color} strokeWidth="11"
          strokeDasharray={`${filled} ${CIRC - filled}`} strokeLinecap="round"
          transform={`rotate(${ROT} ${CX} ${CY})`}
          style={{ transition: 'stroke-dasharray 0.06s linear' }}
        />
      )}

      {/* Center: score */}
      <text x={CX} y={CY + 6}
        textAnchor="middle" fill="#f1f5f9"
        fontSize="38" fontWeight="800"
        fontFamily="-apple-system,'Inter',sans-serif"
      >
        {Math.round(s)}
      </text>

      {/* /100 */}
      <text x={CX} y={CY + 26}
        textAnchor="middle" fill="rgba(255,255,255,0.3)"
        fontSize="12" fontFamily="-apple-system,'Inter',sans-serif"
      >/100</text>

      {/* Level label */}
      <text x={CX} y={CY + 52}
        textAnchor="middle" fill={color}
        fontSize="13" fontWeight="700"
        fontFamily="-apple-system,'Inter',sans-serif"
        letterSpacing="0.5"
      >{level}</text>
    </svg>
  )
}
