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

// Backend-контракт: вместо «нет измерения» приходит JSON null (см. black_box_experiments_schema.json —
// type: ["null", "number"], и backend/app/json_util.py). Поэтому все числовые поля объявлены как `number | null`,
// а чувствительность может быть не только числом, но и объектом с null-границами.
type NumOrNull = number | null
type SensitivityEntry = NumOrNull | { lower?: NumOrNull; upper?: NumOrNull; power_lower?: NumOrNull; power_upper?: NumOrNull }
type Parameter = { name: string; baseline: number; ui_range: { min: number; max: number }; valid_range?: { min: number | null; max: number | null }; critical?: boolean; sensitivity?: Record<string, SensitivityEntry> }
type Metric = { name: string; full: NumOrNull; compressed: NumOrNull; absolute_delta: NumOrNull; relative_delta: NumOrNull; direction: 'higher_is_better' | 'lower_is_better'; kind?: string; definition?: { direction?: string; kind?: string } }
type Model = { model_id: string; parameters: Parameter[]; current_configuration: Record<string, number>; baseline: { configuration: Record<string, number>; metrics: Record<string, NumOrNull> }; metrics: Metric[]; metadata?: { full_model?: string; compressed_model?: string; experiment_id?: string; timestamp?: string }; constraints?: Record<string, string> }
type Support = { score: number; level: string; nearest_experiment_id?: string | null; distance: number }
type Prediction = { prediction_mode?: string; model_id?: string; prediction: Record<string, NumOrNull>; baseline: Record<string, NumOrNull>; configuration: Record<string, number>; support?: Support; metrics?: Metric[]; persisted?: boolean }
type Experiment = { experiment_id: string; timestamp?: string; configuration: Record<string, number>; metrics: Record<string, NumOrNull>; model_id?: string }

// Единственная нормальная форма для чисел из API: null / undefined / NaN / Infinity -> null.
function num(value: NumOrNull | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatValue(value: NumOrNull | undefined, name = '') {
  const n = num(value)
  if (n === null) return '—'
  return name.includes('accuracy') || name.includes('f1') ? n.toFixed(4) : n.toFixed(2)
}
function prettyName(name: string) { return name.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()) }
function deltaClass(delta: number | null | undefined, direction?: string) {
  if (delta === undefined || delta === null || delta === 0) return 'baseline-text'
  const increaseIsBetter = direction !== 'lower_is_better'
  return (delta > 0) === increaseIsBetter ? 'positive' : 'negative'
}
function metricTone(metric: Metric, prediction?: number | null, baseline?: number | null) {
  const p = num(prediction); const b = num(baseline)
  if (p === null || b === null) return 'neutral'
  const better = metric.direction === 'higher_is_better' ? p >= b : p <= b
  const distance = Math.abs(p - b) / (Math.abs(b) || 1)
  return better || distance < 0.01 ? 'good' : distance < 0.05 ? 'warn' : 'bad'
}
// Тон карточки с учётом режима «фактический замер»: зелёная рамка подсказывает,
// что показаны измеренные метрики выбранного эксперимента, а не прогноз модели.
function displayTone(metric: Metric, predicted: number | null, base: number | null, isActual: boolean) {
  const tone = metricTone(metric, predicted, base)
  return isActual ? `${tone} actual` : tone
}
// Ширина полосы: safe-отношение двух чисел с null (нет замера -> минимальная полоса).
function barWidth(value: number | null | undefined, total: number | null | undefined, min = 8) {
  const v = num(value); const t = num(total)
  if (v === null || t === null || t === 0) return min
  return Math.min(100, Math.max(min, (v / t) * 100))
}

export default function Page() {
  const [model, setModel] = useState<Model | null>(null)
  const [config, setConfig] = useState<Record<string, number>>({})
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [experiments, setExperiments] = useState<Experiment[]>([])

  // Санитаризация ответа API: JSON null в числовых слотах (контракт black-box-схемы)
  // не должен приводить к NaN-арифметике и падению рендера.
  const sanitizeModel = (raw: Model): Model => ({
    ...raw,
    parameters: (raw.parameters ?? []).map((p) => ({ ...p, baseline: num(p.baseline) ?? 0 })),
    current_configuration: Object.fromEntries(Object.entries(raw.current_configuration ?? {}).map(([k, v]) => [k, num(v) ?? 0])),
    metrics: (raw.metrics ?? []).map((m) => ({ ...m, full: num(m.full), compressed: num(m.compressed), absolute_delta: num(m.absolute_delta), relative_delta: num(m.relative_delta) })),
    baseline: { configuration: raw.baseline?.configuration ?? {}, metrics: Object.fromEntries(Object.entries(raw.baseline?.metrics ?? {}).map(([k, v]) => [k, num(v)])) },
  })
  const sanitizePrediction = (raw: Prediction): Prediction => ({
    ...raw,
    prediction: Object.fromEntries(Object.entries(raw.prediction ?? {}).map(([k, v]) => [k, num(v)])),
    baseline: Object.fromEntries(Object.entries(raw.baseline ?? {}).map(([k, v]) => [k, num(v)])),
  })
  const sanitizeExperiments = (raw: unknown): Experiment[] => Array.isArray(raw) ? raw.map((e) => ({ ...e, configuration: Object.fromEntries(Object.entries(e?.configuration ?? {}).map(([k, v]: [string, unknown]) => [k, typeof v === 'number' && Number.isFinite(v) ? v : 0])), metrics: Object.fromEntries(Object.entries(e?.metrics ?? {}).map(([k, v]: [string, unknown]) => [k, num(v as number)])) })) : []

  const [health, setHealth] = useState<'loading' | 'online' | 'offline'>('loading')
  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState('')
  const [selectedParam, setSelectedParam] = useState('')
  const parameterRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const selectParameter = (name: string) => {
    setSelectedParam(name)
    // При выборе из рейтинга чувствительности прокрутить список параметров к выбранному
    requestAnimationFrame(() => parameterRefs.current[name]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }
  const [selectedExperiment, setSelectedExperiment] = useState<Experiment | null>(null)
  const requestId = useRef(0)

  const load = useCallback(async () => {
    try {
      const [healthResponse, modelResponse, experimentsResponse] = await Promise.all([
        fetch(`${API_URL}/health`), fetch(`${API_URL}/api/model`), fetch(`${API_URL}/api/experiments`),
      ])
      if (!healthResponse.ok || !modelResponse.ok) throw new Error('Сервер недоступен')
      const nextModel = sanitizeModel(await modelResponse.json() as Model)
      setModel(nextModel); setConfig(nextModel.current_configuration); setHealth('online')
      if (experimentsResponse.ok) setExperiments(sanitizeExperiments(await experimentsResponse.json()))
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
      if (id === requestId.current) setPrediction(sanitizePrediction(body))
    } catch (err) { if (id === requestId.current) setError(err instanceof Error ? err.message : 'Не удалось получить прогноз') }
    finally { if (id === requestId.current) setCalculating(false) }
  }, [])

  useEffect(() => {
    if (!model || !Object.keys(config).length) return
    const timeout = window.setTimeout(() => void predict(config), 220)
    return () => window.clearTimeout(timeout)
  }, [config, model, predict])

  // Слайдер принимает только конечные числа: null/NaN из API не должны
  // попадать в value<input type="range"> (React роняет рендер на NaN).
  const sliderValue = (raw: number | undefined, baseline: number) => {
    const n = num(raw) ?? num(baseline) ?? 0
    return Number.isFinite(n) ? n : 0
  }

  const sensitivity = useMemo(() => model?.parameters.map((parameter) => ({ ...parameter, score: Math.max(...Object.values(parameter.sensitivity || {}).map((value) => { if (typeof value === 'number') return Math.abs(num(value) ?? 0); if (!value) return 0; return Math.max(Math.abs(num(value.lower) ?? 0), Math.abs(num(value.upper) ?? 0), Math.abs(num(value.power_lower) ?? 0), Math.abs(num(value.power_upper) ?? 0)) }), 0) })).sort((a, b) => b.score - a.score) || [], [model])

  const reset = async () => {
    requestId.current += 1
    setCalculating(true); setError(''); setSelectedExperiment(null)
    try {
      const response = await fetch(`${API_URL}/api/reset`, { method: 'POST' })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Не удалось сбросить значения')
      setConfig(sanitizePrediction(body).configuration); setPrediction(sanitizePrediction(body))
    } catch (err) { setError(err instanceof Error ? err.message : 'Не удалось сбросить значения') }
    finally { setCalculating(false) }
  }

  const applyExperiment = (experiment: Experiment) => {
    setSelectedExperiment(experiment)
    setConfig({ ...experiment.configuration })
    // Мгновенно перестраиваем карточки «Оценка качества модели одним взглядом»
    // на фактические метрики выбранного запуска, не дожидаясь ответа /api/predict.
    // Эксперимент — это реальный замер в данной конфигурации, поэтому он и есть
    // наиболее точное значение прогноза; суррогатная модель позже лишь подтвердит его.
    if (Object.keys(experiment.metrics).length) {
      setPrediction((current) => current
        ? { ...current, prediction: { ...current.prediction, ...experiment.metrics }, configuration: { ...experiment.configuration } }
        : current)
    }
    void predict({ ...experiment.configuration })
  }

  // Фиксируем выбранный эксперимент на момент последнего ответа /api/predict.
  // Пока пользователь двигает слайдеры (config !== конфигурация эксперимента),
  // карточки снова показывают прогноз суррогатной модели для текущей конфигурации.
  useEffect(() => {
    if (!prediction || !selectedExperiment) return
    const sameAsExperiment = Object.entries(selectedExperiment.configuration)
      .every(([key, value]) => num(prediction.configuration?.[key]) === value)
    if (!sameAsExperiment) setSelectedExperiment(null)
  }, [prediction, selectedExperiment])

  // Активные метрики для блока «одним взглядом»: при выборе эксперимента берём
  // полный набор из experiment.metrics (в model.json могут отсутствовать метрики,
  // добавленные бэкендом на этапе preprocess), иначе — каталог модели.
  const activeMetrics = useMemo<Metric[]>(() => {
    if (!model) return []
    if (!selectedExperiment) return model.metrics
    const byName = new Map(model.metrics.map((m) => [m.name, m]))
    return Object.entries(selectedExperiment.metrics).map(([name, value]) => {
      const known = byName.get(name)
      return {
        name,
        full: known?.full ?? null,
        compressed: value ?? known?.compressed ?? null,
        absolute_delta: known?.absolute_delta ?? null,
        relative_delta: known?.relative_delta ?? null,
        direction: known?.direction ?? 'higher_is_better',
        kind: known?.kind,
      }
    })
  }, [model, selectedExperiment])

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
            {model?.parameters.map((parameter) => { const value = sliderValue(config[parameter.name], parameter.baseline); const delta = value - parameter.baseline; return <div key={parameter.name} className={`parameter ${selectedParam === parameter.name ? 'selected' : ''}`} onClick={() => selectParameter(parameter.name)} ref={(el) => { parameterRefs.current[parameter.name] = el }}>
              <div className="parameter-top"><div><span className="parameter-name">{prettyName(parameter.name)}</span>{parameter.critical && <span className="critical">критический</span>}</div><strong>{value.toFixed(2)}</strong></div>
              <input aria-label={parameter.name} type="range" min={parameter.ui_range.min} max={parameter.ui_range.max} step="0.01" value={Math.min(Math.max(value, parameter.ui_range.min), parameter.ui_range.max)} onChange={(event) => setConfig((current) => ({ ...current, [parameter.name]: Number(event.target.value) }))} />
              <div className="range-labels"><span>min {parameter.ui_range.min}</span><span>max {parameter.ui_range.max}</span></div>
              <div className="parameter-details"><span>Baseline <strong>{parameter.baseline.toFixed(2)}</strong></span><span>Current <strong>{value.toFixed(2)}</strong></span><span className={deltaClass(delta)}>Delta <strong>{delta === 0 ? '0.00' : `${delta > 0 ? '+' : ''}${delta.toFixed(2)}`}</strong></span></div>
            </div> })}
          </div>
          <div className="sensitivity-box"><div className="box-title"><Target /> Рейтинг чувствительности</div>{sensitivity.map((parameter, index) => <button className="sensitivity-row" key={parameter.name} onClick={() => selectParameter(parameter.name)}><span className="rank">0{index + 1}</span><span>{parameter.name}</span><span className="sensitivity-score">{parameter.score.toFixed(3)} <ChevronRight /></span></button>)}</div>
        </aside>
        <section className="main-column">
          <div className="hero-row"><div><p className="eyebrow">{model?.model_id || 'Модель'} / Анализ в реальном времени</p><h2>Оценка качества модели <span>одним взглядом</span></h2></div><div className="calc-state">{calculating ? <><Loader2 className="spin" /> Расчёт</> : health === 'online' && prediction ? <><Check /> Синхронизировано с backend</> : <><AlertTriangle /> Ожидание backend</>}</div></div>
          <div className="metric-grid">{activeMetrics.map((metric) => { const predicted = num(prediction?.prediction[metric.name] ?? (selectedExperiment ? selectedExperiment.metrics[metric.name] : undefined)); const base = num(prediction?.baseline[metric.name] ?? model?.baseline.metrics[metric.name] ?? metric.compressed); const delta = predicted !== null && base !== null ? predicted - base : undefined; const tone = displayTone(metric, predicted, base, Boolean(selectedExperiment)); return <article className={`metric-card ${tone}`} key={metric.name}><div className="metric-card-head"><span>{prettyName(metric.name)}</span><span className="metric-kind">{metric.kind || 'metric'}</span></div><div className="metric-label">{selectedExperiment ? 'Фактический замер' : 'Прогноз'}</div><div className="metric-value">{formatValue(predicted, metric.name)}</div><div className="metric-comparison"><span>Baseline {formatValue(base, metric.name)}</span><span className={deltaClass(delta, metric.direction)}>{delta === undefined ? '—' : `${delta > 0 ? '+' : ''}${formatValue(delta, metric.name)}`}</span></div><div className="metric-bar"><span style={{ width: `${barWidth(predicted, base)}%` }} /></div></article> })}</div>
          <div className="compare-card panel"><div className="card-heading"><div><p className="eyebrow">Сравнение с исходной моделью</p><h3>Оригинал <span>vs</span> сжатая</h3></div><div className="legend"><span className="legend-dot actual" /> Сжатая версия <span className="legend-dot predicted" /> Прогноз</div></div><div className="comparison-table">{model?.metrics.map((metric) => <div className="comparison-row" key={metric.name}><span className="comparison-name">{prettyName(metric.name)}</span><div className="comparison-line"><span className="line-fill" style={{ width: `${barWidth(Math.abs(num(metric.compressed) ?? 0), Math.abs(num(metric.full) ?? 0), 12)}%` }} /><span className="line-marker" /></div><span className="actual-value">{formatValue(metric.compressed, metric.name)}</span><span className="full-value">{formatValue(metric.full, metric.name)} full</span></div>)}</div></div>
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
