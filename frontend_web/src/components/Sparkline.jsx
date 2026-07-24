import { AreaChart, Area, ResponsiveContainer } from 'recharts'

export default function Sparkline({ data = [], color = '#7c3aed', height = 38 }) {
  if (!data || data.length < 2) {
    return <div style={{ height, opacity: 0.2, background: `${color}22`, borderRadius: 6 }} />
  }
  const points = data.map((v, i) => ({ v, i }))
  const gradId = `sg${color.replace(/[^a-z0-9]/gi, '')}`

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points} margin={{ top: 2, right: 0, left: 0, bottom: 2 }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <Area
          type="monotone" dataKey="v"
          stroke={color} strokeWidth={2}
          fill={`url(#${gradId})`}
          dot={false} isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
