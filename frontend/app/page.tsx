'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Clock3,
  Gauge,
  History,
  Loader2,
  RotateCcw,
  Server,
  SlidersHorizontal,
  Sparkles,
  Target,
  Zap,
} from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_URL || ''

type Parameter = { name: string; baseline: number; ui_range: { min: number; max: number }; critical?: boolean; sensitivity?: Record<string, number | { lower?: number; upper?: number; power_lower?: number; power_upper?: number }> }
type Metric = { name: string; full: number; compressed: number; absolute_delta: number; relative_delta: number; direction: 'higher_is_better' | 'lower_is_better'; kind?: string }
type Model = { model_id: string; parameters: Parameter[]; current_configuration: Record<string, number>; baseline: { configuration: Record<string, number>; metrics: Record<string, number> }; metrics: Metric[]; metadata?: { experiment_id?: string; timestamp?: string } }
type Prediction = { prediction: Record<string, number>; baseline: Record<string, number>; configuration: Record<string, number>; support?: { level: string; score: number; nearest_experiment_id?: string | null; distance?: number }; metrics?: Metric[] }
type Experiment = { experiment_id: string; timestamp?: string; configuration: Record<string, number>; metrics: Record<string, number>; model_id?: string }

function formatValue(value: number | undefined, name = '') {
  if (value === undefined || Number.isNaN(value)) return '—'
  return name.includes('accuracy') || name.includes('f1') ? value.toFixed(4) : value.toFixed(2)
}
function prettyName(name: string) { return name.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }
function metricTone(metric: Metric, prediction?: number, baseline?: number) {
  if (prediction === undefined || baseline === undefined) return 'neutral'
  const better = metric.direction === 'higher_is_better' ? prediction >= baseline : prediction <= baseline
  const distance = Math.abs(prediction - baseline) / (Math.abs(baseline) || 1)
  return better || distance < 0.01 ? 'good' : distance < 0.05 ? 'warn' : 'bad'
}

export default function Page() {
  const [model, setModel] = useState<Model | null>(null)
  const [config, setConfig] = useState<Record<string, number>>({})
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [experiments, setExperiments] = useState<Experiment[]>([])
  const [health, setHealth] = useState<'loading' | 'online' | 'offline'>('loading')
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState('')
  const [selectedParam, setSelectedParam] = useState('')
  const requestId = useRef(0)

  const load = useCallback(async () => {
    try {
      const [healthResponse, modelResponse, experimentsResponse] = await Promise.all([
        fetch(`${API_URL}/health`), fetch(`${API_URL}/api/model`), fetch(`${API_URL}/api/experiments`),
      ])
      if (!healthResponse.ok || !modelResponse.ok) throw new Error('Backend is unavailable')
      const nextModel = await modelResponse.json() as Model
      setModel(nextModel); setConfig(nextModel.current_configuration); setHealth('online')
      if (experimentsResponse.ok) setExperiments(await experimentsResponse.json())
    } catch (err) { setHealth('offline'); setError(err instanceof Error ? err.message : 'Unable to connect to backend') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const predict = useCallback(async (nextConfig: Record<string, number>) => {
    const id = ++requestId.current; setCalculating(true); setError('')
    try {
      const response = await fetch(`${API_URL}/api/predict`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parameters: nextConfig }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Prediction failed')
      if (id === requestId.current) setPrediction(body)
    } catch (err) { if (id === requestId.current) setError(err instanceof Error ? err.message : 'Prediction failed') }
    finally { if (id === requestId.current) setCalculating(false) }
  }, [])

  useEffect(() => {
    if (!model || !Object.keys(config).length) return
    const timeout = window.setTimeout(() => void predict(config), 220)
    return () => window.clearTimeout(timeout)
  }, [config, model, predict])

  const sensitivity = useMemo(() => model?.parameters.map((parameter) => ({ ...parameter, score: Math.max(...Object.values(parameter.sensitivity || {}).map((value) => typeof value === 'number' ? Math.abs(value) : Math.max(Math.abs(value.lower || 0), Math.abs(value.upper || 0), Math.abs(value.power_lower || 0), Math.abs(value.power_upper || 0))), 0) })).sort((a, b) => b.score - a.score) || [], [model])

  const reset = async () => { setCalculating(true); setError(''); try { const response = await fetch(`${API_URL}/api/reset`, { method: 'POST' }); const body = await response.json(); if (!response.ok) throw new Error(body.detail || 'Reset failed'); setConfig(body.configuration); setPrediction(body) } catch (err) { setError(err instanceof Error ? err.message : 'Reset failed') } finally { setCalculating(false) } }

  if (loading) return <main className="loading-screen"><div className="loader-mark"><Activity /></div><p>Connecting to compression lab…</p></main>

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Sparkles /></div><div><p className="eyebrow">Model Lab / Interactive research</p><h1>Compression <span>Workbench</span></h1></div></div>
        <div className="top-actions"><div className={`system-status ${health}`}><span /> System {health === 'online' ? 'operational' : health === 'loading' ? 'checking' : 'offline'}</div><button className="reset-button" onClick={reset} disabled={calculating}><RotateCcw /> Reset to baseline</button></div>
      </header>
      {error && <div className="error-banner"><AlertTriangle /> <span>{error}</span><button onClick={() => setError('')}>Dismiss</button></div>}
      <div className="content-grid">
        <aside className="sidebar panel">
          <div className="section-heading"><div><p className="eyebrow">Configuration</p><h2>Model parameters</h2></div><SlidersHorizontal /></div>
          <p className="muted intro">Tune the compression profile and observe the surrogate prediction in real time.</p>
          <div className="parameter-list">
            {model?.parameters.map((parameter) => { const value = config[parameter.name] ?? parameter.baseline; const delta = value - parameter.baseline; return <div key={parameter.name} className={`parameter ${selectedParam === parameter.name ? 'selected' : ''}`} onClick={() => setSelectedParam(parameter.name)}>
              <div className="parameter-top"><div><span className="parameter-name">{prettyName(parameter.name)}</span>{parameter.critical && <span className="critical">critical</span>}</div><strong>{value.toFixed(2)}</strong></div>
              <input aria-label={parameter.name} type="range" min={parameter.ui_range.min} max={parameter.ui_range.max} step="0.01" value={value} onChange={(event) => setConfig((current) => ({ ...current, [parameter.name]: Number(event.target.value) }))} />
              <div className="range-labels"><span>min {parameter.ui_range.min}</span><span>max {parameter.ui_range.max}</span></div>
              <div className="parameter-details"><span>Baseline <strong>{parameter.baseline.toFixed(2)}</strong></span><span>Current <strong>{value.toFixed(2)}</strong></span><span className={delta === 0 ? 'baseline-text' : delta > 0 ? 'positive' : 'negative'}>Delta <strong>{delta === 0 ? '0.00' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}</strong></span></div>
            </div> })}
          </div>
          <div className="sensitivity-box"><div className="box-title"><Target /> Sensitivity ranking</div>{sensitivity.map((parameter, index) => <button className="sensitivity-row" key={parameter.name} onClick={() => setSelectedParam(parameter.name)}><span className="rank">0{index + 1}</span><span>{parameter.name}</span><span className="sensitivity-score">{parameter.score.toFixed(3)} <ChevronRight /></span></button>)}</div>
        </aside>
        <section className="main-column">
          <div className="hero-row"><div><p className="eyebrow">{model?.model_id || 'Model'} / live analysis</p><h2>Performance <span>at a glance</span></h2></div><div className="calc-state">{calculating ? <><Loader2 className="spin" /> Calculating</> : health === 'online' && prediction ? <><Check /> Synced with backend</> : <><AlertTriangle /> Waiting for backend</>}</div></div>
          <div className="metric-grid">{model?.metrics.map((metric) => { const predicted = prediction?.prediction[metric.name]; const base = prediction?.baseline[metric.name] ?? model.baseline.metrics[metric.name]; const delta = predicted !== undefined && base !== undefined ? predicted - base : undefined; const tone = metricTone(metric, predicted, base); return <article className={`metric-card ${tone}`} key={metric.name}><div className="metric-card-head"><span>{prettyName(metric.name)}</span><span className="metric-kind">{metric.kind || 'metric'}</span></div><div className="metric-value">{formatValue(predicted, metric.name)}</div><div className="metric-comparison"><span>Baseline {formatValue(base, metric.name)}</span><span className={delta !== undefined && delta >= 0 ? 'positive' : 'negative'}>{delta === undefined ? '—' : `${delta >= 0 ? '+' : ''}${formatValue(delta, metric.name)}`}</span></div><div className="metric-bar"><span style={{ width: `${Math.min(100, Math.max(8, base ? (predicted || 0) / base * 100 : 8))}%` }} /></div></article> })}</div>
          <div className="compare-card panel"><div className="card-heading"><div><p className="eyebrow">Reference comparison</p><h3>Original <span>vs</span> compressed</h3></div><div className="legend"><span className="legend-dot actual" /> Actual baseline <span className="legend-dot predicted" /> Predicted</div></div><div className="comparison-table">{model?.metrics.map((metric) => <div className="comparison-row" key={metric.name}><span className="comparison-name">{prettyName(metric.name)}</span><div className="comparison-line"><span className="line-fill" style={{ width: `${Math.min(100, Math.max(12, Math.abs(metric.compressed / (metric.full || 1)) * 100))}%` }} /><span className="line-marker" /></div><span className="actual-value">{formatValue(metric.compressed, metric.name)}</span><span className="full-value">{formatValue(metric.full, metric.name)} full</span></div>)}</div></div>
          <div className="lower-grid"><section className="panel history-card"><div className="card-heading"><div><p className="eyebrow">Saved runs</p><h3>Experiment history</h3></div><History /></div>{experiments.length ? experiments.map((experiment) => <button className="experiment-row" key={experiment.experiment_id} onClick={() => setConfig(experiment.configuration)}><div className="experiment-icon"><Zap /></div><div className="experiment-copy"><strong>{experiment.experiment_id}</strong><span>{experiment.timestamp ? new Date(experiment.timestamp).toLocaleString() : 'Timestamp unavailable'}</span></div><div className="experiment-metric">{formatValue(Object.values(experiment.metrics)[0])}<small>compressed</small></div><ChevronRight /></button>) : <div className="empty-state"><History /> No saved experiments yet</div>}</section><section className="panel support-card"><div className="card-heading"><div><p className="eyebrow">Surrogate model</p><h3>Prediction support</h3></div><Gauge /></div><div className={`support-level ${(prediction?.support?.level || 'unknown').toLowerCase()}`}>{prediction?.support?.level || 'pending'}</div>{prediction?.support?.level?.toLowerCase() === 'low' && <div className="support-warning"><AlertTriangle /> Low support: treat this prediction as an estimate outside the strongest experiment coverage.</div>}<p className="muted">How well the current configuration is covered by existing experiments.</p><div className="support-meta"><span>Nearest run</span><strong>{prediction?.support?.nearest_experiment_id || '—'}</strong></div><div className="support-meta"><span>Distance</span><strong>{prediction?.support?.distance?.toFixed(3) || '—'}</strong></div></section></div>
          <section className="grafana-section panel"><div className="card-heading"><div><p className="eyebrow">Observability</p><h3>Actual vs predicted <span>over time</span></h3></div><div className="grafana-label"><Activity /> Grafana live</div></div>{GRAFANA_URL ? <iframe src={GRAFANA_URL} title="Grafana dashboard" className="grafana-frame" /> : <div className="grafana-placeholder"><Server /><span>Set <code>NEXT_PUBLIC_GRAFANA_DASHBOARD_URL</code> to connect the dashboard.</span></div>}</section>
        </section>
      </div>
      <footer><span><Clock3 /> Backend predictions persist automatically</span><span>API · {API_URL.replace(/^https?:\/\//, '')}</span></footer>
    </main>
  )
}
