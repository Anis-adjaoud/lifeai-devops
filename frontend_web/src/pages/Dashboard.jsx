import { useState, useEffect, useCallback } from 'react'
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import RadialGauge from '../components/RadialGauge.jsx'
import ScoreRing    from '../components/ScoreRing.jsx'
import NutritionSummary from '../components/NutritionSummary.jsx'
import UsagePanel from '../components/UsagePanel.jsx'
import { getProfile, getSessions, getPatterns, getTrend, getMetrics, runAnalysis, getDiary } from '../api/client.js'
import { useGoogleFitConnect } from '../hooks/useGoogleFitConnect'

/* ── helpers ── */
function getLevel(s) {
  if (s >= 80) return { label: 'Excellent', cls: 'lvl-excellent', color: '#10b981' }
  if (s >= 65) return { label: 'Bon',       cls: 'lvl-bon',       color: '#6366f1' }
  if (s >= 45) return { label: 'Attention', cls: 'lvl-attention', color: '#f59e0b' }
  return              { label: 'Critique',  cls: 'lvl-critique',  color: '#ef4444' }
}
function fmtDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit' })
}
function fmtDay(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getDate()).padStart(2,'0')}/${String(d.getMonth()+1).padStart(2,'0')}`
}

/* ── ScoreCard ── */
const SCORE_CFG = {
  activity:  { label:'Activité',  icon:'🏃', color:'#10b981', bg:'rgba(16,185,129,0.08)',  border:'rgba(16,185,129,0.22)' },
  sleep:     { label:'Sommeil',   icon:'😴', color:'#6366f1', bg:'rgba(99,102,241,0.08)',  border:'rgba(99,102,241,0.22)' },
  nutrition: { label:'Nutrition', icon:'🥗', color:'#f59e0b', bg:'rgba(245,158,11,0.08)',  border:'rgba(245,158,11,0.22)' },
  risk:      { label:'Résistance', icon:'🛡', color:'#ef4444', bg:'rgba(239,68,68,0.08)',   border:'rgba(239,68,68,0.22)' },
}

function ScoreCard({ type, score, history = [] }) {
  const cfg = SCORE_CFG[type]
  const lv  = getLevel(score ?? 0)
  // La couleur de l'anneau s'adapte au niveau (donc au pourcentage) : vert / bleu / orange / rouge.
  const color = lv.color
  const prev = history.length >= 2 ? history[history.length - 2] : null
  const delta = (prev != null && score != null) ? +(score - prev).toFixed(1) : null

  return (
    <div className="score-card" style={{ background: `${color}0d`, border: `1px solid ${color}28` }}>
      <div className="sc-head">
        <div className="sc-icon" style={{ background: `${color}22` }}>{cfg.icon}</div>
        <span className="sc-label">{cfg.label}</span>
        {delta !== null && Math.abs(delta) > 0.05 && (
          <span className="sc-delta" style={{
            marginLeft: 'auto',
            background: delta > 0.4 ? 'rgba(16,185,129,0.14)' : delta < -0.4 ? 'rgba(239,68,68,0.14)' : 'rgba(148,163,184,0.1)',
            color: delta > 0.4 ? '#10b981' : delta < -0.4 ? '#ef4444' : '#94a3b8',
          }}>
            {delta > 0.4 ? '↑' : delta < -0.4 ? '↓' : '→'} {Math.abs(delta)}
          </span>
        )}
      </div>

      <ScoreRing score={score} color={color} />

      <span className="sc-badge" style={{ background: `${color}1a`, color }}>
        {lv.label}
      </span>
    </div>
  )
}

/* ── CustomTooltip for area chart ── */
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'rgba(12,12,28,0.95)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: 10, padding: '10px 14px', fontSize: 12
    }}>
      <div style={{ color: '#94a3b8', marginBottom: 6, fontSize: 11 }}>{label}</div>
      {payload.map(p => (
        <div key={p.dataKey} style={{ color: p.color, display:'flex', gap:8, marginBottom:3 }}>
          <span style={{ fontWeight:600 }}>{p.dataKey}</span>
          <span>{p.value?.toFixed(1)}</span>
        </div>
      ))}
    </div>
  )
}

/* ── Google Fit section ── */
const DAY_LABELS = ['il y a 6j','il y a 5j','il y a 4j','il y a 3j','Avant-hier','Hier','Auj.']

function buildDayData(arr7, key) {
  if (!Array.isArray(arr7) || arr7.length === 0) return []
  const days = arr7.slice(-7)
  const today = new Date()
  return days.map((val, i) => {
    const d = new Date(today)
    d.setDate(today.getDate() - (days.length - 1 - i))
    const label = i === days.length - 1 ? 'Auj.'
      : i === days.length - 2 ? 'Hier'
      : d.toLocaleDateString('fr-FR', { weekday: 'short' }).replace('.','')
    return { day: label, [key]: Math.round(val) }
  })
}

function MetricCard({ icon, label, value, unit, color, sub }) {
  return (
    <div style={{
      background: `${color}0d`, border: `1px solid ${color}28`,
      borderRadius: 14, padding: '16px 18px',
      display: 'flex', flexDirection: 'column', gap: 4,
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:2 }}>
        <span style={{ fontSize:20 }}>{icon}</span>
        <span style={{ fontSize:10, fontWeight:700, textTransform:'uppercase',
          letterSpacing:'0.7px', color:'var(--text-3)' }}>{label}</span>
      </div>
      <div style={{ fontSize:30, fontWeight:800, color, lineHeight:1 }}>
        {value != null ? value.toLocaleString('fr-FR') : '—'}
        <span style={{ fontSize:13, fontWeight:500, color:'var(--text-2)', marginLeft:4 }}>{unit}</span>
      </div>
      {sub && <div style={{ fontSize:11, color:'var(--text-3)', marginTop:2 }}>{sub}</div>}
    </div>
  )
}

function _toArr(v) {
  if (Array.isArray(v)) return v
  if (typeof v === 'string') { try { return JSON.parse(v) } catch { return [] } }
  return []
}

function GoogleFitSection({ metrics }) {
  const last = metrics[0]  // most recent entry

  const steps7d = _toArr(last?.steps_7d)
  const sleep7d  = _toArr(last?.sleep_7d)

  // Build 7-day data using the last entry's 7d arrays
  const stepsData = buildDayData(steps7d, 'steps')
  const sleepData  = buildDayData(sleep7d,  'heures')

  // steps goal: 10 000 / day
  const STEPS_GOAL = 10000
  const stepsGoalPct = last?.steps_today ? Math.min(100, Math.round((last.steps_today / STEPS_GOAL) * 100)) : 0

  // 7-day averages
  const avgSteps = steps7d.length
    ? Math.round(steps7d.reduce((a,b)=>a+b,0) / steps7d.length)
    : null
  const avgSleep = sleep7d.length
    ? +(sleep7d.reduce((a,b)=>a+b,0) / sleep7d.length).toFixed(1)
    : null

  const CustomBarTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null
    return (
      <div style={{ background:'rgba(12,12,28,0.95)', border:'1px solid rgba(255,255,255,0.1)',
        borderRadius:8, padding:'8px 12px', fontSize:12 }}>
        <div style={{ color:'#94a3b8', marginBottom:3 }}>{label}</div>
        {payload.map(p => (
          <div key={p.dataKey} style={{ color: p.fill, fontWeight:600 }}>
            {p.value?.toLocaleString('fr-FR')} {p.dataKey === 'steps' ? 'pas' : 'h'}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
      {/* Section title */}
      <div style={{ display:'flex', alignItems:'center', gap:10 }}>
        <div style={{ fontSize:14, fontWeight:700, color:'var(--text-2)',
          textTransform:'uppercase', letterSpacing:'0.7px' }}>
          Données Google Fit
        </div>
        <div style={{ fontSize:11, color:'var(--text-3)',
          background:'rgba(255,255,255,0.04)', border:'1px solid rgba(255,255,255,0.07)',
          padding:'2px 9px', borderRadius:20 }}>
          {fmtDate(last?.date)}
        </div>
      </div>

      {/* 4 metric cards */}
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12 }}>
        <MetricCard
          icon="👣" label="Pas aujourd'hui" color="#10b981"
          value={last?.steps_today} unit="pas"
          sub={`${stepsGoalPct}% de l'objectif · moy 7j : ${avgSteps?.toLocaleString('fr-FR') ?? '—'}`}
        />
        <MetricCard
          icon="😴" label="Sommeil dernière nuit" color="#6366f1"
          value={last?.sleep_hours} unit="h"
          sub={`Recommandé : 7–9h · moy 7j : ${avgSleep ?? '—'}h`}
        />
        <MetricCard
          icon="⚡" label="Minutes actives" color="#f59e0b"
          value={last?.active_minutes} unit="min"
          sub="OMS : 30 min/j minimum"
        />
        <MetricCard
          icon="🔥" label="Calories brûlées" color="#ef4444"
          value={last?.calories || null} unit="kcal"
          sub={last?.heart_rate ? `FC repos : ${last.heart_rate} bpm` : last?.weight_kg ? `Poids : ${last.weight_kg} kg` : ''}
        />
      </div>

      {/* Steps + Sleep charts */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:14 }}>
        {/* Steps bar chart */}
        <div className="chart-card">
          <div className="chart-head">
            <div className="chart-title">👣 Pas quotidiens — 7 jours</div>
            {avgSteps && (
              <span style={{ fontSize:11, color:'#10b981' }}>
                Moy : {avgSteps.toLocaleString('fr-FR')}
              </span>
            )}
          </div>
          {stepsData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={stepsData} margin={{ top:4, right:8, left:-10, bottom:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false}/>
                <XAxis dataKey="day" tick={{ fill:'#475569', fontSize:11 }} axisLine={false} tickLine={false}/>
                <YAxis tick={{ fill:'#475569', fontSize:10 }} axisLine={false} tickLine={false}
                  tickFormatter={v => v >= 1000 ? `${(v/1000).toFixed(0)}k` : v}/>
                <Tooltip content={<CustomBarTooltip />}/>
                <ReferenceLine y={STEPS_GOAL} stroke="rgba(16,185,129,0.3)"
                  strokeDasharray="4 4" label={{ value:'10k objectif', fill:'rgba(16,185,129,0.5)', fontSize:10, position:'insideTopRight' }}/>
                <Bar dataKey="steps" radius={[5,5,0,0]}>
                  {stepsData.map((entry, i) => (
                    <Cell key={i}
                      fill={entry.steps >= STEPS_GOAL ? '#10b981' : entry.steps >= STEPS_GOAL * 0.7 ? '#f59e0b' : '#ef4444'}
                      fillOpacity={i === stepsData.length - 1 ? 1 : 0.7}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state" style={{ padding:'24px 0' }}>
              <div style={{ fontSize:24, marginBottom:6 }}>👣</div>
              <div style={{ fontSize:12, color:'var(--text-3)' }}>Pas de données de pas</div>
            </div>
          )}
        </div>

        {/* Sleep bar chart */}
        <div className="chart-card">
          <div className="chart-head">
            <div className="chart-title">😴 Sommeil — 7 nuits</div>
            {avgSleep && (
              <span style={{ fontSize:11, color:'#6366f1' }}>Moy : {avgSleep}h</span>
            )}
          </div>
          {sleepData.length > 0 ? (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={sleepData} margin={{ top:4, right:8, left:-10, bottom:0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false}/>
                <XAxis dataKey="day" tick={{ fill:'#475569', fontSize:11 }} axisLine={false} tickLine={false}/>
                <YAxis domain={[0, 10]} tick={{ fill:'#475569', fontSize:10 }} axisLine={false} tickLine={false}
                  tickFormatter={v => `${v}h`}/>
                <Tooltip content={<CustomBarTooltip />}/>
                <ReferenceLine y={7} stroke="rgba(99,102,241,0.3)" strokeDasharray="4 4"
                  label={{ value:'7h objectif', fill:'rgba(99,102,241,0.5)', fontSize:10, position:'insideTopRight' }}/>
                <Bar dataKey="heures" radius={[5,5,0,0]}>
                  {sleepData.map((entry, i) => (
                    <Cell key={i}
                      fill={entry.heures >= 7 ? '#6366f1' : entry.heures >= 6 ? '#f59e0b' : '#ef4444'}
                      fillOpacity={i === sleepData.length - 1 ? 1 : 0.7}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state" style={{ padding:'24px 0' }}>
              <div style={{ fontSize:24, marginBottom:6 }}>😴</div>
              <div style={{ fontSize:12, color:'var(--text-3)' }}>Pas de données de sommeil</div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/* ── AnalysisReport panel ── */
function AnalysisReport({ report, onClose }) {
  if (!report) return null
  const lv = getLevel(report.global_score ?? 0)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: '24px',
    }} onClick={onClose}>
      <div style={{
        background: 'linear-gradient(160deg, rgba(20,20,44,0.98), rgba(12,12,28,0.99))',
        border: '1px solid rgba(124,58,237,0.3)',
        borderRadius: 22, padding: '36px 40px',
        maxWidth: 700, width: '100%', maxHeight: '88vh', overflowY: 'auto',
        boxShadow: '0 24px 80px rgba(0,0,0,0.8), 0 0 40px rgba(124,58,237,0.15)',
        scrollbarWidth: 'thin',
      }} onClick={e => e.stopPropagation()}>

        {/* Header */}
        <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start', marginBottom:28 }}>
          <div>
            <div style={{ fontSize:12, color:'var(--text-3)', textTransform:'uppercase',
              letterSpacing:'1px', marginBottom:6 }}>Rapport d'analyse LifeAI</div>
            <div style={{ display:'flex', alignItems:'center', gap:14 }}>
              <div style={{ fontSize:48, fontWeight:900, color: lv.color, lineHeight:1 }}>
                {report.global_score?.toFixed(1) ?? '—'}
              </div>
              <div>
                <span style={{
                  background: `${lv.color}20`, color: lv.color,
                  border: `1px solid ${lv.color}40`,
                  padding: '4px 14px', borderRadius: 20, fontSize: 13, fontWeight: 700,
                }}>{lv.label}</span>
                <div style={{ fontSize:11, color:'var(--text-3)', marginTop:5 }}>
                  {fmtDate(report.date)}
                </div>
              </div>
            </div>
          </div>
          <button onClick={onClose} style={{
            background:'rgba(255,255,255,0.06)', border:'1px solid var(--border)',
            color:'var(--text-2)', width:36, height:36, borderRadius:10,
            cursor:'pointer', fontSize:18, display:'flex', alignItems:'center', justifyContent:'center',
          }}>×</button>
        </div>

        {/* Alertes */}
        {report.alerts?.length > 0 && (
          <div style={{ marginBottom:20 }}>
            {report.alerts.map((a, i) => (
              <div key={i} style={{
                background:'rgba(239,68,68,0.08)', border:'1px solid rgba(239,68,68,0.22)',
                borderRadius:10, padding:'10px 14px', marginBottom:8,
                display:'flex', gap:10, alignItems:'flex-start',
              }}>
                <span style={{ fontSize:16 }}>⚠️</span>
                <span style={{ fontSize:13, color:'#fca5a5' }}>{a}</span>
              </div>
            ))}
          </div>
        )}

        {/* Synthèse */}
        {report.synthesis && (
          <div style={{
            background:'rgba(124,58,237,0.07)', border:'1px solid rgba(124,58,237,0.18)',
            borderRadius:14, padding:'18px 20px', marginBottom:18,
          }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--purple-light)',
              textTransform:'uppercase', letterSpacing:'0.7px', marginBottom:10 }}>
              📋 Synthèse
            </div>
            <p style={{ fontSize:14, lineHeight:1.75, color:'var(--text)', margin:0 }}>
              {report.synthesis}
            </p>
          </div>
        )}

        {/* Action prioritaire */}
        {report.priority_action && (
          <div style={{
            background:'rgba(16,185,129,0.07)', border:'1px solid rgba(16,185,129,0.2)',
            borderRadius:14, padding:'16px 20px', marginBottom:18,
            display:'flex', gap:14, alignItems:'flex-start',
          }}>
            <span style={{ fontSize:24, flexShrink:0 }}>🎯</span>
            <div>
              <div style={{ fontSize:11, fontWeight:700, color:'#10b981',
                textTransform:'uppercase', letterSpacing:'0.7px', marginBottom:6 }}>
                Action prioritaire
              </div>
              <p style={{ fontSize:14, color:'var(--text)', margin:0, lineHeight:1.6 }}>
                {report.priority_action}
              </p>
            </div>
          </div>
        )}

        {/* Plan semaine */}
        {report.weekly_plan?.length > 0 && (
          <div style={{ marginBottom:18 }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text-2)',
              textTransform:'uppercase', letterSpacing:'0.7px', marginBottom:12 }}>
              📅 Plan de la semaine
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              {report.weekly_plan.map((item, i) => (
                <div key={i} style={{
                  background:'rgba(255,255,255,0.03)', border:'1px solid var(--border)',
                  borderRadius:10, padding:'10px 14px',
                  display:'flex', gap:12, alignItems:'flex-start',
                }}>
                  <div style={{
                    width:22, height:22, borderRadius:6, flexShrink:0,
                    background:'rgba(124,58,237,0.2)', border:'1px solid rgba(124,58,237,0.3)',
                    display:'flex', alignItems:'center', justifyContent:'center',
                    fontSize:11, fontWeight:700, color:'var(--purple-light)',
                  }}>{i+1}</div>
                  <span style={{ fontSize:13, color:'var(--text)', lineHeight:1.55 }}>{item}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Scores détaillés */}
        <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:10, marginBottom:18 }}>
          {[
            { label:'Activité',  score: report.activity_score,  color:'#10b981' },
            { label:'Sommeil',   score: report.sleep_score,     color:'#6366f1' },
            { label:'Nutrition', score: report.nutrition_score, color:'#f59e0b' },
            { label:'Risque',    score: report.risk_score,      color:'#ef4444' },
          ].map(({ label, score, color }) => (
            <div key={label} style={{
              background:`${color}0d`, border:`1px solid ${color}25`,
              borderRadius:12, padding:'12px 14px', textAlign:'center',
            }}>
              <div style={{ fontSize:24, fontWeight:800, color, lineHeight:1 }}>
                {score?.toFixed(1) ?? '—'}
              </div>
              <div style={{ fontSize:11, color:'var(--text-3)', marginTop:4 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Prédiction */}
        {report.prediction && (
          <div style={{
            background:'rgba(99,102,241,0.06)', border:'1px solid rgba(99,102,241,0.18)',
            borderRadius:14, padding:'14px 18px',
            display:'flex', gap:12, alignItems:'flex-start',
          }}>
            <span style={{ fontSize:20 }}>🔮</span>
            <div>
              <div style={{ fontSize:11, fontWeight:700, color:'#6366f1',
                textTransform:'uppercase', letterSpacing:'0.7px', marginBottom:5 }}>
                Prédiction ML — 7 jours
              </div>
              <p style={{ fontSize:13, color:'var(--text-2)', margin:0, lineHeight:1.6 }}>
                {report.prediction}
              </p>
              {report.ml_risks && (
                <div style={{ display:'flex', gap:8, marginTop:10, flexWrap:'wrap' }}>
                  {[
                    ['low_activity_risk',     'Sédentarité'],
                    ['sleep_debt_risk',       'Dette de sommeil'],
                    ['activity_decline_risk', "Baisse d'activité"],
                  ].map(([key, label]) => {
                    const r = report.ml_risks[key]
                    if (!r) return null
                    const color = r.risk_level === 'high'   ? '#ef4444'
                                : r.risk_level === 'medium' ? '#f59e0b'
                                :                              '#22c55e'
                    return (
                      <div key={key} style={{
                        background:`${color}12`, border:`1px solid ${color}30`,
                        borderRadius:10, padding:'6px 10px', minWidth:110,
                      }}>
                        <div style={{ fontSize:10, color:'var(--text-3)', textTransform:'uppercase',
                          letterSpacing:'0.4px' }}>{label}</div>
                        <div style={{ fontSize:15, fontWeight:800, color }}>
                          {Math.round(r.probability * 100)}%
                          <span style={{ fontSize:10, fontWeight:600, marginLeft:5, opacity:0.85 }}>
                            {r.risk_level}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
        )}

        <UsagePanel usage={report.usage} />
      </div>
    </div>
  )
}

/* ── Main Dashboard ── */
export default function Dashboard({ userId, onGoToNutrition }) {
  const [profile,  setProfile]  = useState({})
  const [sessions, setSessions] = useState([])
  const [patterns, setPatterns] = useState([])
  const [trend,    setTrend]    = useState({})
  const [metrics,  setMetrics]  = useState([])
  const [diary,    setDiary]    = useState(null)  // journal alimentaire du jour
  const [days,     setDays]     = useState(14)
  const [loading,  setLoading]  = useState(false)
  const [error,    setError]    = useState('')
  const [initLoad, setInitLoad] = useState(true)
  const [report,   setReport]   = useState(null)   // modal

  const load = useCallback(async () => {
    let sessions = []
    try {
      const [p, s, pt, tr, mx, nut] = await Promise.all([
        getProfile(userId), getSessions(userId, 60),
        getPatterns(userId), getTrend(userId),
        getMetrics(userId, 30),
        getDiary(userId).catch(() => null),
      ])
      setProfile(p); setSessions(s); setPatterns(pt); setTrend(tr); setMetrics(mx)
      setDiary(nut)
      setError('')
      sessions = s
    } catch (e) {
      // Échec de chargement (ex: session expirée → 401)
      const msg = e.message || ''
      setError(
        msg.toLowerCase().includes('authentifi') || msg.toLowerCase().includes('401')
          ? 'Session expirée — reconnectez-vous.'
          : 'Impossible de charger le dashboard — réessaie dans un instant.'
      )
    }
    setInitLoad(false)
    return sessions
  }, [userId])

  useEffect(() => { setInitLoad(true); load() }, [load])

  const handleAnalyze = async () => {
    setLoading(true); setError('')
    try {
      const result = await runAnalysis(userId)
      await load()  // rafraichit `sessions` (donc `last` = sessions[0]) depuis la vraie base
      if (result && result.global_score != null) {
        setReport(result)
      }
    }
    catch (e) { setError(e.message) }
    finally { setLoading(false) }
  }

  const { connect: handleReconnect } = useGoogleFitConnect(() => setError(''))

  const isTokenError = error.toLowerCase().includes('expir') || error.toLowerCase().includes('reconnectez')

  const last = sessions[0]

  // Une seule entrée par jour (la plus récente) — sessions est déjà trié DESC
  const dailyMap = new Map()
  for (const s of sessions) {
    const day = fmtDay(s.date)
    if (!dailyMap.has(day)) dailyMap.set(day, s)
  }
  const dailySessions = [...dailyMap.values()].reverse()  // chronologique
  const rev = dailySessions  // utilisé pour les sparklines

  /* chart data (last N days) */
  const chartData = dailySessions.slice(-days).map(s => ({
    date: fmtDay(s.date),
    Global:    +(s.global_score    ?? 0).toFixed(1),
    Activité:  +(s.activity_score  ?? 0).toFixed(1),
    Sommeil:   +(s.sleep_score     ?? 0).toFixed(1),
    // null (pas de données ce jour-là) reste null — trou dans la courbe, pas un 0
    Nutrition: s.nutrition_score != null ? +s.nutrition_score.toFixed(1) : null,
    Risque:    +(s.risk_score      ?? 0).toFixed(1),
  }))

  /* sparkline histories */
  const histories = {
    activity:  rev.map(s => s.activity_score),
    sleep:     rev.map(s => s.sleep_score),
    nutrition: rev.map(s => s.nutrition_score),
    risk:      rev.map(s => s.risk_score),
  }

  /* trend display */
  const delta = trend.delta
  const trendDir = delta == null ? 'flat' : delta > 1 ? 'up' : delta < -1 ? 'down' : 'flat'
  const trendLabel = trendDir === 'up' ? `↑ +${delta}` : trendDir === 'down' ? `↓ ${delta}` : '→ Stable'

  if (initLoad) return (
    <div className="page">
      <div className="dash-gap">
        <div className="dash-top">
          {[0,1,2,3].map(i => (
            <div key={i} className="card card-p" style={{ height: 200 }}>
              <div className="skeleton" style={{ height:12, width:'50%', marginBottom:12 }} />
              <div className="skeleton" style={{ height:32, width:'40%', marginBottom:8 }} />
              <div className="skeleton" style={{ height:10, width:'70%' }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )

  return (
    <div className="page">
      {report && <AnalysisReport report={report} onClose={() => setReport(null)} />}
      <div className="dash-gap">
        {error && (
          <div className="error-banner" style={{ display:'flex', alignItems:'center', justifyContent:'space-between', gap:12 }}>
            <span>⚠ {error}</span>
            {isTokenError && (
              <button onClick={handleReconnect} style={{
                flexShrink:0, padding:'6px 16px', borderRadius:8, border:'none',
                background:'rgba(16,185,129,0.2)', color:'#10b981',
                fontSize:12, fontWeight:600, cursor:'pointer', whiteSpace:'nowrap',
              }}>
                🔗 Reconnecter Google Fit
              </button>
            )}
          </div>
        )}

        {/* Bandeau non-bloquant : journal alimentaire du jour vide */}
        {!initLoad && diary?.totals?.entries === 0 && (
          <div className="nutri-banner">
            <span className="nutri-banner-icon">🥗</span>
            <div className="nutri-banner-text">
              <strong>Ton journal alimentaire du jour est vide.</strong>
              <span> Google Fit ne suit pas ton alimentation — ajoute tes repas pour un score plus juste.</span>
            </div>
            {onGoToNutrition && (
              <button className="nutri-banner-btn" onClick={onGoToNutrition}>
                Ouvrir le journal
              </button>
            )}
          </div>
        )}

        {/* ── Row 1: Gauge + 3 stat cards ── */}
        <div className="dash-top">
          {/* Gauge */}
          <div className="gauge-card">
            <div className="gauge-title">Score Global</div>
            <RadialGauge score={last?.global_score ?? null} />
            {last && (
              <div style={{ fontSize:11, color:'var(--text-3)', marginTop:4, textAlign:'center' }}>
                Mis à jour le {fmtDate(last.date)}
              </div>
            )}
            <button
              className={`analyze-btn${loading ? ' running' : ''}`}
              onClick={handleAnalyze}
              disabled={loading}
              style={{ marginTop:16, width:'100%', justifyContent:'center' }}
            >
              {loading
                ? <><span className="spinner">⟳</span> Analyse en cours...</>
                : <><span>🔄</span> Lancer une analyse</>
              }
            </button>
            {last?.synthesis && (
              <button
                onClick={() => setReport(last)}
                style={{
                  marginTop:8, width:'100%', justifyContent:'center',
                  background:'rgba(124,58,237,0.12)', border:'1px solid rgba(124,58,237,0.3)',
                  color:'var(--purple-light)', borderRadius:10, padding:'8px 0',
                  fontSize:12, fontWeight:600, cursor:'pointer',
                  display:'flex', alignItems:'center', gap:6,
                }}
              >
                📋 Voir le dernier rapport
              </button>
            )}
            <button onClick={handleReconnect} style={{
              marginTop:8, width:'100%',
              background:'rgba(255,255,255,0.03)', border:'1px solid rgba(255,255,255,0.07)',
              color:'var(--text-3)', borderRadius:10, padding:'7px 0',
              fontSize:11, cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', gap:6,
            }}>
              🔗 Reconnecter Google Fit
            </button>
          </div>

          {/* Trend */}
          <div className="stat-card">
            <div className="stat-label">Tendance 7 jours</div>
            <div className="stat-value" style={{ fontSize:18 }}>
              {trend.trend || '—'}
            </div>
            {delta !== null && (
              <span className={`stat-trend ${trendDir}`}>{trendLabel} pts</span>
            )}
            <div className="stat-sub" style={{ marginTop:8 }}>
              Basé sur {trend.sessions_count ?? 0} analyse{trend.sessions_count !== 1 ? 's' : ''}
            </div>
          </div>

          {/* Last session */}
          <div className="stat-card">
            <div className="stat-label">Dernière analyse</div>
            {last ? (
              <>
                <div className="stat-value" style={{ fontSize:22, color: getLevel(last.global_score ?? 0).color }}>
                  {(last.global_score ?? 0).toFixed(1)}
                </div>
                <span className="stat-trend flat" style={{ width:'fit-content' }}>
                  {getLevel(last.global_score ?? 0).label}
                </span>
                <div className="stat-sub" style={{ marginTop:8 }}>{fmtDate(last.date)}</div>
              </>
            ) : (
              <div className="stat-sub">Aucune session</div>
            )}
          </div>

          {/* Sessions count */}
          <div className="stat-card">
            <div className="stat-label">Total analyses</div>
            <div className="stat-value">{trend.sessions_count ?? 0}</div>
            <div className="stat-sub">
              {profile.name && `Bonjour ${profile.name} 👋`}
            </div>
            {profile.goals && (
              <div style={{ marginTop:10, fontSize:12, color:'var(--purple-light)',
                background:'rgba(124,58,237,0.1)', borderRadius:8, padding:'6px 10px' }}>
                🎯 {Array.isArray(profile.goals) ? profile.goals[0] : profile.goals}
              </div>
            )}
          </div>
        </div>

        {/* ── Row 2: 4 score cards ── */}
        <div className="dash-scores">
          {(['activity','sleep','nutrition','risk']).map(type => (
            <ScoreCard
              key={type}
              type={type}
              score={last ? last[`${type}_score`] : null}
              history={histories[type]}
            />
          ))}
        </div>

        {/* ── Nutrition du jour (anneau calories + macros) ── */}
        {diary && (
          <div className="section-header" style={{ marginBottom: 0, marginTop: 4 }}>
            <div className="section-title">🥗 Nutrition du jour</div>
            {onGoToNutrition && (
              <button className="action-btn" onClick={onGoToNutrition}>Ouvrir le journal →</button>
            )}
          </div>
        )}
        {diary && <NutritionSummary diary={diary} />}

        {/* ── Row 3: Google Fit raw metrics ── */}
        {metrics.length > 0 && <GoogleFitSection metrics={metrics} />}

        {/* ── Row 4: Area chart ── */}
        <div className="chart-card">
          <div className="chart-head">
            <div className="chart-title">📈 Évolution des scores</div>
            <div className="toggle-group">
              {[7,14,30].map(d => (
                <button
                  key={d}
                  className={`toggle-btn${days === d ? ' active' : ''}`}
                  onClick={() => setDays(d)}
                >{d}j</button>
              ))}
            </div>
          </div>
          {chartData.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📊</div>
              <div className="empty-title">Pas encore assez de données</div>
              <div className="empty-sub">Lance une analyse pour commencer le suivi</div>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <AreaChart data={chartData} margin={{ top:4, right:8, left:-10, bottom:0 }}>
                <defs>
                  {[
                    ['Global',    '#7c3aed'],
                    ['Activité',  '#10b981'],
                    ['Sommeil',   '#6366f1'],
                    ['Nutrition', '#f59e0b'],
                    ['Risque',    '#ef4444'],
                  ].map(([k,c]) => (
                    <linearGradient key={k} id={`cg${k}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor={c} stopOpacity={0.22} />
                      <stop offset="95%" stopColor={c} stopOpacity={0.01} />
                    </linearGradient>
                  ))}
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill:'#475569', fontSize:11 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0,100]} tick={{ fill:'#475569', fontSize:11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize:12, paddingTop:12, color:'#94a3b8' }}
                  iconType="circle" iconSize={8}
                />
                <Area type="monotone" dataKey="Global"    stroke="#7c3aed" strokeWidth={2.5} fill="url(#cgGlobal)"    dot={false} />
                <Area type="monotone" dataKey="Activité"  stroke="#10b981" strokeWidth={1.5} fill="url(#cgActivité)"  dot={false} />
                <Area type="monotone" dataKey="Sommeil"   stroke="#6366f1" strokeWidth={1.5} fill="url(#cgSommeil)"   dot={false} />
                <Area type="monotone" dataKey="Nutrition" stroke="#f59e0b" strokeWidth={1.5} fill="url(#cgNutrition)" dot={false} />
                <Area type="monotone" dataKey="Risque"    stroke="#ef4444" strokeWidth={1.5} fill="url(#cgRisque)"    dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* ── Row 4: Synthèse dernière analyse ── */}
        {/* Affiche toujours la vraie derniere session (sessions[0], re-fetchee a chaque load()) */}
        {last?.synthesis && (() => {
          const d = last
          return (
            <div style={{
              background: 'rgba(124,58,237,0.06)', border: '1px solid rgba(124,58,237,0.2)',
              borderRadius: 18, padding: '24px 28px', cursor: 'pointer',
            }} onClick={() => setReport(last)}>
              <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:16 }}>
                <div style={{ display:'flex', alignItems:'center', gap:10 }}>
                  <span style={{ fontSize:18 }}>📋</span>
                  <span style={{ fontSize:13, fontWeight:700, color:'var(--purple-light)',
                    textTransform:'uppercase', letterSpacing:'0.7px' }}>
                    Dernière analyse — {fmtDate(d.date)}
                  </span>
                </div>
                <span style={{ fontSize:11, color:'var(--text-3)',
                  background:'rgba(255,255,255,0.05)', border:'1px solid var(--border)',
                  padding:'3px 10px', borderRadius:20 }}>
                  Voir le rapport complet →
                </span>
              </div>

              {/* Score global */}
              {d.global_score != null && (
                <div style={{ display:'flex', gap:20, marginBottom:d.synthesis ? 16 : 0 }}>
                  {[
                    { label:'Global',    score: d.global_score,    color:'#7c3aed' },
                    { label:'Activité',  score: d.activity_score,  color:'#10b981' },
                    { label:'Sommeil',   score: d.sleep_score,     color:'#6366f1' },
                    { label:'Nutrition', score: d.nutrition_score, color:'#f59e0b' },
                    { label:'Risque',    score: d.risk_score,      color:'#ef4444' },
                  ].map(({ label, score, color }) => (
                    <div key={label} style={{ textAlign:'center', minWidth:60 }}>
                      <div style={{ fontSize:22, fontWeight:800, color, lineHeight:1 }}>
                        {score?.toFixed(1) ?? '—'}
                      </div>
                      <div style={{ fontSize:10, color:'var(--text-3)', marginTop:3,
                        textTransform:'uppercase', letterSpacing:'0.5px' }}>{label}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Synthèse */}
              {d.synthesis ? (
                <p style={{ fontSize:14, lineHeight:1.8, color:'var(--text)', margin:'0 0 16px' }}>
                  {d.synthesis}
                </p>
              ) : (
                <p style={{ fontSize:13, color:'var(--text-3)', fontStyle:'italic', margin:'12px 0 16px' }}>
                  Synthèse narrative non disponible pour cette analyse.
                  Relancez une analyse pour obtenir une synthèse complète.
                </p>
              )}

              {/* Action prioritaire */}
              {d.priority_action && (
                <div style={{
                  display:'flex', gap:12, alignItems:'flex-start',
                  background:'rgba(16,185,129,0.07)', border:'1px solid rgba(16,185,129,0.18)',
                  borderRadius:12, padding:'12px 16px', marginBottom:16,
                }}>
                  <span style={{ fontSize:20 }}>🎯</span>
                  <div>
                    <div style={{ fontSize:11, fontWeight:700, color:'#10b981',
                      textTransform:'uppercase', letterSpacing:'0.6px', marginBottom:4 }}>
                      Action prioritaire
                    </div>
                    <p style={{ fontSize:13, color:'var(--text)', margin:0, lineHeight:1.6 }}>
                      {d.priority_action}
                    </p>
                  </div>
                </div>
              )}

              {/* Plan semaine condensé */}
              {d.weekly_plan?.length > 0 && (
                <div>
                  <div style={{ fontSize:11, fontWeight:700, color:'var(--text-3)',
                    textTransform:'uppercase', letterSpacing:'0.6px', marginBottom:10 }}>
                    📅 Plan de la semaine
                  </div>
                  <div style={{ display:'grid', gridTemplateColumns:'repeat(2,1fr)', gap:8 }}>
                    {d.weekly_plan.map((item, i) => (
                      <div key={i} style={{
                        background:'rgba(255,255,255,0.03)', border:'1px solid var(--border)',
                        borderRadius:9, padding:'9px 12px',
                        display:'flex', gap:10, alignItems:'flex-start',
                      }}>
                        <span style={{ fontSize:12, color:'var(--purple-light)',
                          fontWeight:700, flexShrink:0 }}>{i+1}</span>
                        <span style={{ fontSize:12, color:'var(--text-2)', lineHeight:1.5 }}>{item}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })()}

        {/* ── Row 5: Patterns ── */}
        <div className="dash-bottom">
          {/* Patterns pleine largeur */}
          <div className="chart-card" style={{ gridColumn: '1 / -1' }}>
            <div className="chart-head">
              <div className="chart-title">⚠ Patterns détectés</div>
              {patterns.length > 0 && (
                <span style={{ fontSize:11, color:'var(--text-3)' }}>
                  {patterns.length} pattern{patterns.length > 1 ? 's' : ''}
                </span>
              )}
            </div>
            {patterns.length === 0 ? (
              <div className="empty-state" style={{ padding:'32px 20px' }}>
                <div className="empty-icon" style={{ fontSize:36 }}>✅</div>
                <div className="empty-title">Aucun pattern récurrent</div>
                <div className="empty-sub">Tout semble aller bien !</div>
              </div>
            ) : (
              <div className="pattern-list">
                {patterns.map((p, i) => {
                  const type = p.pattern_type || ''
                  const isWarn = type.includes('low') || type.includes('critique') || type.includes('risque')
                  return (
                    <div key={i} className="pattern-item">
                      <div className="pattern-icon-wrap" style={{
                        background: isWarn ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)'
                      }}>
                        {isWarn ? '🔴' : '⚠️'}
                      </div>
                      <div>
                        <div className="pattern-text">{p.description}</div>
                        <div className="pattern-meta">
                          Détecté {p.occurrences}× · Dernier : {fmtDay(p.last_seen)}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
