'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import GrafanaDashboard from '../components/GrafanaDashboard/GrafanaDashboard'
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
  SlidersHorizontal,
  Sparkles,
  Target,
  Zap,
} from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.VITE_API_URL || '/backend'
const GRAFANA_DASHBOARD_DEFAULT = 'http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk'
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_URL || process.env.VITE_GRAFANA_DASHBOARD_URL || GRAFANA_DASHBOARD_DEFAULT

type SensitivityEntry = number | { lower?: number; upper?: number; power_lower?: number; power_upper?: number }
type Parameter = { name: string; baseline: number; ui_range: { min: number; max: number }; valid_range?: { min: number | null; max: number | null }; critical?: boolean; sensitivity?: Record<string, SensitivityEntry> }
type Metric = { name: string; full: number; compressed: number; absolute_delta: number; relative_delta: number | null; direction: 'higher_is_better' | 'lower_is_better'; kind?: string; definition?: { direction?: string; kind?: string } }
type Model = { model_id: string; parameters: Parameter[]; current_configuration: Record<string, number>; baseline: { configuration: Record<string, number>; metrics: Record<string, number> }; metrics: Metric[]; metadata?: { full_model?: string; compressed_model?: string; experiment_id?: string; timestamp?: string }; constraints?: Record<string, string> }
type Support = { score: number; level: string; nearest_experiment_id?: string | null; distance: number }
type Prediction = { prediction_mode?: string; model_id?: string; prediction: Record<string, number>; baseline: Record<string, number>; configuration: Record<string, number>; support?: Support; metrics?: Metric[]; persisted?: boolean }
type Experiment = { experiment_id: string; timestamp?: string; configuration: Record<string, number>; metrics: Record<string, number>; model_id?: string }

function formatValue(value: number | undefined, name = '') {
  if (value === undefined || Number.isNaN(value)) return '—'
  return name.includes('accuracy') || name.includes('f1') ? value.toFixed(4) : value.toFixed(2)
}
function prettyName(name: string) { return name.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }
function deltaClass(delta: number | undefined, direction?: string) {
  if (delta === undefined || delta === 0) return 'baseline-text'
  const increaseIsBetter = direction !== 'lower_is_better'
  return (delta > 0) === increaseIsBetter ? 'positive' : 'negative'
}
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
  const [selectedExperiment, setSelectedExperiment] = useState<Experiment | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    try {
      const [healthResponse, modelResponse, experimentsResponse] = await Promise.all([
        fetch(`${API_URL}/health`), fetch(`${API_URL}/api/model`), fetch(`${API_URL}/api/experiments`),
      ])
      if (!healthResponse.ok || !modelResponse.ok) throw new Error('Сервер недоступен')
      const nextModel = await modelResponse.json() as Model
      setModel(nextModel); setConfig(nextModel.current_configuration); setHealth('online')
      if (experimentsResponse.ok) setExperiments(await experimentsResponse.json())
    } catch (err) { setHealth('offline'); setError(err instanceof Error ? err.message : 'Сейчас сервер отключен') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const predict = useCallback(async (nextConfig: Record<string, number>) => {
    const id = ++requestId.current; setCalculating(true); setError('')
    try {
      const response = await fetch(`${API_URL}/api/predict`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parameters: nextConfig }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Не удалось получить прогноз')
      if (id === requestId.current) setPrediction(body)
    } catch (err) { if (id === requestId.current) setError(err instanceof Error ? err.message : 'Не удалось получить прогноз') }
    finally { if (id === requestId.current) setCalculating(false) }
  }, [])

  useEffect(() => {
    if (!model || !Object.keys(config).length) return
    const timeout = window.setTimeout(() => void predict(config), 220)
    return () => window.clearTimeout(timeout)
  }, [config, model, predict])

  const sensitivity = useMemo(() => model?.parameters.map((parameter) => ({ ...parameter, score: Math.max(...Object.values(parameter.sensitivity || {}).map((value) => typeof value === 'number' ? Math.abs(value) : Math.max(Math.abs(value.lower || 0), Math.abs(value.upper || 0), Math.abs(value.power_lower || 0), Math.abs(value.power_upper || 0))), 0) })).sort((a, b) => b.score - a.score) || [], [model])

  const reset = async () => {
    requestId.current += 1
    setCalculating(true); setError(''); setSelectedExperiment(null)
    try {
      const response = await fetch(`${API_URL}/api/reset`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Не удалось сбросить значения')
      setConfig(body.configuration); setPrediction(body)
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сбросить значения') }
    finally { setCalculating(false) }
  }

  const applyExperiment = (experiment: Experiment) => {
    setSelectedExperiment(experiment)
    setConfig({ ...experiment.configuration })
    void predict({ ...experiment.configuration })
  }

  if (loading) return <main className="loading-screen"><div className="loader-mark"><Activity /></div><p>Подключение к лаборатории сжатия…</p></main>

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><Sparkles /></div><div><p className="eyebrow">Лаборатория моделей / Интерактивное исследование</p><h1>Workbench <span>сжатия</span></h1></div></div>
        <div className="top-actions"><div className={`system-status ${health}`}><span /> Система {health === 'online' ? 'в норме' : health === 'loading' ? 'проверяется' : 'офлайн'}</div><button className="reset-button" onClick={reset} disabled={calculating}><RotateCcw /> Сбросить к базовым значениям</button></div>
      </header>
      {error && <div className="error-banner"><AlertTriangle /> <span>{error}</span><button onClick={() => setError('')}>Скрыть</button></div>}
      <div className="content-grid">
        <aside className="sidebar panel">
          <div className="section-heading"><div><p className="eyebrow">Конфигурация</p><h2>Параметры модели</h2></div><SlidersHorizontal /></div>
          <p className="muted intro">Настройте профиль сжатия и наблюдайте прогноз суррогатной модели в реальном времени.</p>
          <div className="parameter-list">
            {model?.parameters.map((parameter) => { const value = config[parameter.name] ?? parameter.baseline; const delta = value - parameter.baseline; return <div key={parameter.name} className={`parameter ${selectedParam === parameter.name ? 'selected' : ''}`} onClick={() => setSelectedParam(parameter.name)}>
              <div className="parameter-top"><div><span className="parameter-name">{prettyName(parameter.name)}</span>{parameter.critical && <span className="critical">критический</span>}</div><strong>{value.toFixed(2)}</strong></div>
              <input aria-label={parameter.name} type="range" min={parameter.ui_range.min} max={parameter.ui_range.max} step="0.01" value={value} onChange={(event) => setConfig((current) => ({ ...current, [parameter.name]: Number(event.target.value) }))} />
              <div className="range-labels"><span>min {parameter.ui_range.min}</span><span>max {parameter.ui_range.max}</span></div>
              <div className="parameter-details"><span>Baseline <strong>{parameter.baseline.toFixed(2)}</strong></span><span>Current <strong>{value.toFixed(2)}</strong></span><span className={deltaClass(delta)}>Delta <strong>{delta === 0 ? '0.00' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}</strong></span></div>
            </div> })}
          </div>
          <div className="sensitivity-box"><div className="box-title"><Target /> Рейтинг чувствительности</div>{sensitivity.map((parameter, index) => <button className="sensitivity-row" key={parameter.name} onClick={() => setSelectedParam(parameter.name)}><span className="rank">0{index + 1}</span><span>{parameter.name}</span><span className="sensitivity-score">{parameter.score.toFixed(3)} <ChevronRight /></span></button>)}</div>
        </aside>
        <section className="main-column">
          <div className="hero-row"><div><p className="eyebrow">{model?.model_id || 'Модель'} / Анализ в реальном времени</p><h2>Оценка качества модели <span>одним взглядом</span></h2></div><div className="calc-state">{calculating ? <><Loader2 className="spin" /> Расчёт</> : health === 'online' && prediction ? <><Check /> Синхронизировано с backend</> : <><AlertTriangle /> Ожидание backend</>}</div></div>
          <div className="metric-grid">{model?.metrics.map((metric) => { const predicted = prediction?.prediction[metric.name]; const base = prediction?.baseline[metric.name] ?? model.baseline.metrics[metric.name]; const delta = predicted !== undefined && base !== undefined ? predicted - base : undefined; const tone = metricTone(metric, predicted, base); return <article className={`metric-card ${tone}`} key={metric.name}><div className="metric-card-head"><span>{prettyName(metric.name)}</span><span className="metric-kind">{metric.kind || 'metric'}</span></div><div className="metric-label">Прогноз</div><div className="metric-value">{formatValue(predicted, metric.name)}</div><div className="metric-comparison"><span>Baseline {formatValue(base, metric.name)}</span><span className={deltaClass(delta, metric.direction)}>{delta === undefined ? '—' : `${delta > 0 ? '+' : ''}${formatValue(delta, metric.name)}`}</span></div><div className="metric-bar"><span style={{ width: `${Math.min(100, Math.max(8, base ? (predicted || 0) / base * 100 : 8))}%` }} /></div></article> })}</div>
          <div className="compare-card panel"><div className="card-heading"><div><p className="eyebrow">Сравнение с исходной моделью</p><h3>Оригинал <span>vs</span> сжатая</h3></div><div className="legend"><span className="legend-dot actual" /> Сжатая версия <span className="legend-dot predicted" /> Прогноз</div></div><div className="comparison-table">{model?.metrics.map((metric) => <div className="comparison-row" key={metric.name}><span className="comparison-name">{prettyName(metric.name)}</span><div className="comparison-line"><span className="line-fill" style={{ width: `${Math.min(100, Math.max(12, Math.abs(metric.compressed / (metric.full || 1)) * 100))}%` }} /><span className="line-marker" /></div><span className="actual-value">{formatValue(metric.compressed, metric.name)}</span><span className="full-value">{formatValue(metric.full, metric.name)} full</span></div>)}</div></div>
          <div className="lower-grid"><section className="panel history-card"><div className="card-heading"><div><p className="eyebrow">Сохранённые запуски</p><h3>История экспериментов</h3></div><History /></div>{experiments.length ? experiments.map((experiment) => <button className={`experiment-row ${selectedExperiment?.experiment_id === experiment.experiment_id ? 'active' : ''}`} key={experiment.experiment_id} onClick={() => applyExperiment(experiment)}><div className="experiment-icon"><Zap /></div><div className="experiment-copy"><strong>{experiment.experiment_id}</strong><span>{experiment.timestamp ? new Date(experiment.timestamp).toLocaleString() : 'Метка времени недоступна'}</span></div><div className="experiment-metric">{formatValue(Object.values(experiment.metrics)[0])}<small>compressed</small></div><ChevronRight /></button>) : <div className="empty-state"><History /> Сохранённых экспериментов пока нет</div>}{selectedExperiment && <div className="actual-reference"><div className="actual-reference-title"><Activity /> Фактические метрики {selectedExperiment.experiment_id} (измеренный запуск)</div><div className="actual-reference-grid">{Object.entries(selectedExperiment.metrics).map(([name, value]) => { const predicted = prediction?.prediction[name]; return <div className="actual-reference-row" key={name}><span>{prettyName(name)}</span><strong className="actual-value">{formatValue(value, name)}</strong><span className="predicted-ref">pred {formatValue(predicted, name)}</span></div> })}</div></div>}</section><section className="panel support-card"><div className="card-heading"><div><p className="eyebrow">Суррогатная модель</p><h3>Точность прогноза</h3></div><Gauge /></div><div className={`support-level ${(prediction?.support?.level || 'unknown').toLowerCase()}`}>{prediction?.support?.level || 'pending'}</div>{prediction?.support?.level?.toLowerCase() === 'low' && <div className="support-warning"><AlertTriangle /> Низкая поддержка: относитесь к этому прогнозу как к оценке за пределами надёжного покрытия экспериментами.</div>}<p className="muted">Уровень поддержки текущей конфигурации существующими экспериментами</p><div className="support-meta"><span>Ближайший эксперимент</span><strong>{prediction?.support?.nearest_experiment_id || '—'}</strong></div><div className="support-meta"><span>Разница</span><strong>{prediction?.support?.distance?.toFixed(3) || '—'}</strong></div></section></div>
          {/* Секция Grafana: iframe вынесен в отдельный компонент (см.
              components/GrafanaDashboard), URL — только из environment. */}
          <section className="grafana-section panel"><div className="card-heading"><div><p className="eyebrow">Наглядно</p><h3>Полная и сжатая модели </h3></div><div className="grafana-label"><Activity /> Grafana live</div></div><GrafanaDashboard url={GRAFANA_URL} /></section>
        </section>
      </div>
      <footer><span><Clock3 /> Прогнозы backend сохраняются автоматически</span><span>API · {API_URL.replace(/^https?:\/\//, '')}</span></footer>
    </main>
  )
}
