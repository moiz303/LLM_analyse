'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import GrafanaDashboard, { requestGrafanaRefresh } from '../components/GrafanaDashboard/GrafanaDashboard'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronRight,
  Gauge,
  History,
  Moon,
  Sun,
  RotateCcw,
  SlidersHorizontal,
  Target,
  Zap,
} from 'lucide-react'

const API_URL = process.env.NEXT_PUBLIC_API_URL || process.env.VITE_API_URL || '/backend'
const GRAFANA_DASHBOARD_DEFAULT = 'http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk'
const GRAFANA_URL = process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_URL || process.env.VITE_GRAFANA_DASHBOARD_URL || GRAFANA_DASHBOARD_DEFAULT

type NumOrNull = number | null
type SensitivityEntry = NumOrNull | { lower?: NumOrNull; upper?: NumOrNull; power_lower?: NumOrNull; power_upper?: NumOrNull }
type Parameter = { name: string; baseline: number; ui_range: { min: number; max: number }; valid_range?: { min: number | null; max: number | null }; critical?: boolean; sensitivity?: Record<string, SensitivityEntry> }
type Metric = { name: string; full: NumOrNull; compressed: NumOrNull; absolute_delta: NumOrNull; relative_delta: NumOrNull; direction: 'higher_is_better' | 'lower_is_better'; kind?: string; definition?: { direction?: string; kind?: string } }
type Model = { model_id: string; parameters: Parameter[]; current_configuration: Record<string, number>; baseline: { configuration: Record<string, number>; metrics: Record<string, NumOrNull> }; metrics: Metric[]; metadata?: { full_model?: string; compressed_model?: string; experiment_id?: string; timestamp?: string }; constraints?: Record<string, string> }
type Support = { score: number; level: string; nearest_experiment_id?: string | null; distance: number }
type Prediction = { prediction_mode?: string; model_id?: string; prediction: Record<string, NumOrNull>; baseline: Record<string, NumOrNull>; configuration: Record<string, number>; support?: Support; metrics?: Metric[]; persisted?: boolean }
type Experiment = { experiment_id: string; timestamp?: string; configuration: Record<string, number>; metrics: Record<string, NumOrNull>; model_id?: string }

function num(value: NumOrNull | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function formatValue(value: NumOrNull | undefined, name = '') {
  const n = num(value)
  if (n === null) return '—'
  return name.includes('accuracy') || name.includes('f1') ? Number(n.toFixed(4)).toLocaleString('ru-RU') : Number(n.toFixed(2)).toLocaleString('ru-RU')
}
function formatParameterValue(value: number) {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 8 })
}
function parameterStep(parameter: Parameter) {
  const span = parameter.ui_range.max - parameter.ui_range.min
  if (Number.isInteger(parameter.baseline) && span >= 1) return 1
  const decimalPlaces = parameter.baseline.toFixed(8).replace(/0+$/, '').split('.')[1]?.length ?? 0
  const rangePrecision = span > 0 ? -Math.floor(Math.log10(span / 100)) : 2
  return 10 ** -Math.max(2, decimalPlaces, rangePrecision)
}
const labels: Record<string, string> = {
  imatrix_chunks: 'Блоки матрицы важности (Imatrix chunks)',
  imatrix_context: 'Контекст матрицы важности (Imatrix context)',
  minimum_nll_gain: 'Минимальное улучшение NLL (Minimum NLL gain)',
  search_rounds: 'Раунды поиска (Search rounds)',
  seed: 'Начальное зерно (Seed)',
  strict_max_bytes: 'Предельный размер, байт (Strict max bytes)',
  target_bytes: 'Целевой размер, байт (Target bytes)',
  model_size_bytes: 'Размер модели, байт',
  model_size_decimal_gb: 'Размер модели, ГБ',
  selection_perplexity: 'Перплексия (Perplexity)',
  selection_nll: 'Логарифмическая потеря (NLL)',
  accuracy_top1: 'Точность первого ответа (Top-1 accuracy)',
  latency_ms: 'Задержка, мс (Latency)',
  quality: 'Качество', memory: 'Память', latency: 'Задержка', generic: 'Метрика',
  high: 'Высокая', medium: 'Средняя', low: 'Низкая', pending: 'Ожидание', unknown: 'Нет данных',
  baseline: 'Базовая конфигурация',
}
function prettyName(name: string) { return labels[name] ?? name }
function experimentName(id: string) {
  if (id === 'baseline') return prettyName(id)
  const adaptiveSize = id.match(/_adaptive_(\d+)_/i)?.[1]
  if (adaptiveSize) return `Адаптивное сжатие · ${(Number(adaptiveSize) / 100).toLocaleString('ru-RU')} ГБ`
  if (id.includes('_q4_k_m_')) return 'Квантование (Q4_K_M)'
  const size = id.match(/_(\d+(?:\.\d+)?)gb_/i)?.[1]
  return size ? `Эксперимент · ${size.replace('.', ',')} ГБ` : `Эксперимент · ${id}`
}
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
function displayTone(metric: Metric, predicted: number | null, base: number | null, isActual: boolean) {
  const tone = metricTone(metric, predicted, base)
  return isActual ? `${tone} actual` : tone
}
function barWidth(value: number | null | undefined, total: number | null | undefined, min = 8) {
  const v = num(value); const t = num(total)
  if (v === null || t === null || t === 0) return min
  return Math.min(100, Math.max(min, (v / t) * 100))
}

export default function Page() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')
  useEffect(() => { setTheme(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light') }, [])
  const toggleTheme = () => {
    const next = theme === 'light' ? 'dark' : 'light'
    setTheme(next)
    document.documentElement.dataset.theme = next
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', next === 'dark' ? '#191c19' : '#e7e8e6')
    try { localStorage.setItem('llm-theme', next) } catch { /* Тема работает и без хранилища. */ }
  }
  const [model, setModel] = useState<Model | null>(null)
  const [config, setConfig] = useState<Record<string, number>>({})
  const [prediction, setPrediction] = useState<Prediction | null>(null)
  const [experiments, setExperiments] = useState<Experiment[]>([])

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

  const [loading, setLoading] = useState(true)
  const [calculating, setCalculating] = useState(false)
  const [error, setError] = useState('')
  const [selectedParam, setSelectedParam] = useState('')
  const parameterRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const selectParameter = (name: string) => {
    setSelectedParam(name)
    requestAnimationFrame(() => parameterRefs.current[name]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }))
  }
  const [selectedExperiment, setSelectedExperiment] = useState<Experiment | null>(null)

  const findKnownExperiment = useCallback((candidate: Record<string, number>): Experiment | null => {
    const keys = Object.keys(candidate)
    if (!keys.length) return null
    const matches = (configuration: Record<string, number>) => keys.every((key) => num(configuration[key]) === num(candidate[key]))
    if (!model) return experiments.find((experiment) => matches(experiment.configuration)) ?? null
    const baselinePoint: Experiment = { experiment_id: 'baseline', configuration: model.baseline?.configuration ?? {}, metrics: Object.fromEntries(model.metrics.map((m) => [m.name, m.compressed])) }
    const list: (Experiment | undefined)[] = [baselinePoint, ...experiments]
    return list.find((experiment) => experiment && matches(experiment.configuration)) ?? null
  }, [model, experiments])

  const activeExperiment = useMemo(() => findKnownExperiment(config), [config, findKnownExperiment])
  const requestId = useRef(0)
  const load = useCallback(async () => {
    try {
      const [healthResponse, modelResponse, experimentsResponse] = await Promise.all([
        fetch(`${API_URL}/health`), fetch(`${API_URL}/api/model`), fetch(`${API_URL}/api/experiments`),
      ])
      if (!healthResponse.ok || !modelResponse.ok) throw new Error('Сервер недоступен')
      const nextModel = sanitizeModel(await modelResponse.json() as Model)
      setModel(nextModel); setConfig(nextModel.current_configuration)
      if (experimentsResponse.ok) setExperiments(sanitizeExperiments(await experimentsResponse.json()))
    } catch (err) { setError(err instanceof Error ? err.message : 'Сейчас сервер отключен') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { void load() }, [load])

  const predict = useCallback(async (nextConfig: Record<string, number>) => {
    const id = ++requestId.current; setCalculating(true); setError('')
    try {
      const response = await fetch(`${API_URL}/api/predict`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ parameters: nextConfig }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Не удалось получить прогноз')
      if (id === requestId.current) {
        setPrediction(sanitizePrediction(body))
        requestGrafanaRefresh(GRAFANA_URL)
      }
    } catch (err) { if (id === requestId.current) setError(err instanceof Error ? err.message : 'Не удалось получить прогноз') }
    finally { if (id === requestId.current) setCalculating(false) }
  }, [])

  useEffect(() => {
    if (!model || !Object.keys(config).length) return
    const timeout = window.setTimeout(() => void predict(config), 220)
    return () => window.clearTimeout(timeout)
  }, [config, model, predict])

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
    if (Object.keys(experiment.metrics).length) {
      setPrediction((current) => current
        ? { ...current, prediction: { ...current.prediction, ...experiment.metrics }, configuration: { ...experiment.configuration } }
        : current)
    }
    void predict({ ...experiment.configuration })
  }

  const highlightedExperimentId = activeExperiment?.experiment_id ?? selectedExperiment?.experiment_id ?? null

  useEffect(() => {
    if (!prediction || !selectedExperiment) return
    const sameAsPrediction = Object.entries(selectedExperiment.configuration)
      .every(([key, value]) => num(prediction.configuration?.[key]) === value)
    if (!sameAsPrediction) setSelectedExperiment(null)
  }, [prediction, selectedExperiment])

  const activeMetrics = useMemo<Metric[]>(() => {
    if (!model) return []
    if (!activeExperiment) return model.metrics
    const byName = new Map(model.metrics.map((m) => [m.name, m]))
    return Object.entries(activeExperiment.metrics).map(([name, value]) => {
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
  }, [model, activeExperiment])

  const comparisonRows = useMemo(() => {
    if (!model) return []
    const actualValues = activeExperiment?.metrics
    const predictedValues = !activeExperiment && prediction && Object.keys(prediction.prediction).length ? prediction.prediction : null
    const names = [...new Set([...model.metrics.map((m) => m.name), ...Object.keys(actualValues ?? {}), ...Object.keys(predictedValues ?? {})])]
    return names.map((name) => {
      const known = model.metrics.find((m) => m.name === name)
      const full = num(known?.full)
      const isBaselinePoint = activeExperiment?.experiment_id === 'baseline'
      const compressed = num((isBaselinePoint ? undefined : actualValues?.[name]) ?? predictedValues?.[name] ?? known?.compressed)
      return { name, full, compressed, isPrediction: predictedValues !== null && name in predictedValues }
    })
  }, [model, activeExperiment, prediction])

  const supportDisplay = useMemo(() => {
    if (!model) return null
    if (activeExperiment) {
      return { level: 'high', nearest_experiment_id: activeExperiment.experiment_id, distance: 0, exact: true }
    }
    const spanned = model.parameters.map((p) => Math.max(p.ui_range.max - p.ui_range.min, 1e-9))
    const knownConfigs = [model.baseline?.configuration ?? {}, ...experiments.map((e) => e.configuration)]
    let best: { id: string; distance: number } | null = null
    for (const configuration of knownConfigs) {
      const id = knownConfigs.indexOf(configuration) === 0 ? 'baseline' : experiments[knownConfigs.indexOf(configuration) - 1]?.experiment_id ?? 'unknown'
      const sumSq = model.parameters.reduce((acc, p, i) => {
        const candidate = num(configuration[p.name]) ?? num(p.baseline) ?? 0
        const diff = ((num(config[p.name]) ?? candidate) - candidate) / spanned[i]
        return acc + diff * diff
      }, 0)
      const distance = Math.sqrt(sumSq / Math.max(model.parameters.length, 1))
      if (!best || distance < best.distance) best = { id, distance }
    }
    if (!best) return null
    const score = Math.max(0, Math.min(1, 1 - best.distance))
    const level = score >= 0.8 ? 'high' : score >= 0.5 ? 'medium' : 'low'
    return { level, nearest_experiment_id: best.id, distance: best.distance, exact: false }
  }, [model, experiments, config, activeExperiment])

  if (loading) return <main className="loading-screen"><div className="loader-mark"><Activity /></div><p>Загрузка…</p></main>

  return (
    <main className="app-shell">
      {error && <div className="error-banner"><AlertTriangle /> <span>{error}</span><button onClick={() => setError('')}>Скрыть</button></div>}
      <div className="content-grid">
        <aside className="sidebar panel" id="parameters">
          <div className="section-heading"><div><h2>Параметры модели</h2></div><SlidersHorizontal /></div>
          <div className="parameter-list">
            {model?.parameters.map((parameter) => {const range = parameter.ui_range; const value = sliderValue(config[parameter.name], parameter.baseline); const delta = value - parameter.baseline; return <div key={parameter.name} className={`parameter ${selectedParam === parameter.name ? 'selected' : ''}`} onClick={() => selectParameter(parameter.name)} ref={(el) => { parameterRefs.current[parameter.name] = el }}>
              <div className="parameter-top"><div><span className="parameter-name">{prettyName(parameter.name)}</span>{parameter.critical && <span className="critical">Критический</span>}</div><strong>{formatParameterValue(value)}</strong></div>
              <input aria-label={prettyName(parameter.name)} type="range" min={range.min} max={range.max} step={parameterStep(parameter)} value={Math.min(Math.max(value, range.min), range.max)} onChange={(event) => setConfig((current) => ({ ...current, [parameter.name]: Number(event.target.value) }))} />
              <div className="range-labels"><span>Мин. {formatParameterValue(range.min)}</span><span>Макс. {formatParameterValue(range.max)}</span></div>
              <div className="parameter-details"><span>Базовое <strong>{formatParameterValue(parameter.baseline)}</strong></span><span>Текущее <strong>{formatParameterValue(value)}</strong></span><span className={deltaClass(delta)}>Изменение <strong>{delta === 0 ? '0' : `${delta > 0 ? '+' : ''}${formatParameterValue(delta)}`}</strong></span></div>
            </div> })}
          </div>
          <div className="sensitivity-box"><div className="box-title"><Target />Чувствительность (Sensitivity)</div>{sensitivity.map((parameter, index) => <button className="sensitivity-row" key={parameter.name} onClick={() => selectParameter(parameter.name)}><span className="rank">0{index + 1}</span><span>{prettyName(parameter.name)}</span><span className="sensitivity-score">{formatParameterValue(parameter.score)} <ChevronRight /></span></button>)}</div>
        </aside>
        <section className="main-column">
          <div className="hero-row" id="assessment"><div><p className="eyebrow">{model?.model_id || 'Модель'}</p><h2>Оценка качества модели</h2></div><div className="hero-actions"><button className="theme-toggle" onClick={toggleTheme} aria-label={theme === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему'} aria-pressed={theme === 'dark'} title={theme === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему'}>{theme === 'light' ? <Moon /> : <Sun />}<span>{theme === 'light' ? 'Тёмная тема' : 'Светлая тема'}</span></button><button className="reset-button" onClick={reset} disabled={calculating}><RotateCcw />Вернуть базовые значения</button></div></div>
          <div className="metric-grid">{activeMetrics.filter((metric) => {if (metric.kind === 'quality' || metric.kind === 'generic') {return true} if (metric.kind === 'memory' || metric.kind === 'latency') {const value = num(prediction?.prediction[metric.name] ?? (activeExperiment? activeExperiment.metrics[metric.name]: undefined)); const minValue = Math.min(...activeMetrics.filter((m) => m.kind === metric.kind).map((m) => num(prediction?.prediction[m.name] ?? (activeExperiment ? activeExperiment.metrics[m.name]: undefined))).filter((v) => v !== null)); return value !== null && value === minValue;} return true;}).map((metric) => {const predicted = num(prediction?.prediction[metric.name] ?? (activeExperiment ? activeExperiment.metrics[metric.name] : undefined));const base = num(prediction?.baseline[metric.name] ?? model?.baseline.metrics[metric.name] ?? metric.compressed);const delta = predicted !== null && base !== null ? predicted - base: undefined;const tone = displayTone(metric,predicted,base,Boolean(activeExperiment));return (<article className={`metric-card ${tone}`} key={metric.name}><div className="metric-card-head">{prettyName(metric.name)}<span className="metric-kind">{prettyName(metric.kind || 'generic')}</span></div><div className="metric-label">{activeExperiment ? experimentName(activeExperiment.experiment_id): 'Прогноз'}</div><div className="metric-value">{formatValue(predicted, metric.name)}</div><div className="metric-comparison"><span>Базовое {formatValue(base, metric.name)}</span><span className={deltaClass(delta, metric.direction)}>{delta === undefined ? '—': `${delta > 0 ? '+' : ''}${formatValue(delta,metric.name)}`}</span></div><div className="metric-bar"><span style={{width: `${barWidth(predicted, base)}%`,}}/></div></article>)})}</div>
          <div className="compare-card panel"><div className="card-heading"><div><h2>Исходная и сравниваемая модели</h2></div><div className="legend">{activeExperiment ? <><span className="legend-dot actual" />{experimentName(activeExperiment.experiment_id)}</> : <><span className="legend-dot predicted" />Прогноз</>}</div></div><div className="comparison-table">{comparisonRows.filter((row) => {if (row.kind === 'quality' || row.kind === 'generic') {return true} if (row.kind === 'memory' || row.kind === 'latency') {const value = num(row.compressed ?? row.full); const minValue = Math.min(...comparisonRows.filter((r) => r.kind === row.kind).map((r) => num(r.compressed ?? r.full)).filter((v) => v !== null)); return value !== null && value === minValue;} return true;}).map((row) => <div className="comparison-row" key={row.name}><span className="comparison-name">{prettyName(row.name)}</span><div className="comparison-line"><span className={`line-fill${row.isPrediction ? ' predicted' : ''}`} style={{ width: `${barWidth(Math.abs(row.compressed ?? 0), Math.abs(num(row.full) ?? 0), 12)}%` }} /><span className="line-marker" /></div><span className="actual-value">{formatValue(row.compressed, row.name)}</span><span className="full-value">{formatValue(row.full, row.name)}</span></div>)}</div></div>          <div className="lower-grid"><section className="panel history-card" id="experiments"><div className="card-heading"><div><h2>История экспериментов</h2></div><History /></div>{experiments.length ? experiments.map((experiment) => <button className={`experiment-row ${highlightedExperimentId === experiment.experiment_id ? 'active' : ''}`} key={experiment.experiment_id} onClick={() => applyExperiment(experiment)}><div className="experiment-icon"><Zap /></div><div className="experiment-copy"><strong title={experiment.experiment_id}>{experimentName(experiment.experiment_id)}</strong><span>{experiment.timestamp ? new Date(experiment.timestamp).toLocaleString('ru-RU') : 'Время не указано'}</span></div><div className="experiment-metric">{formatValue(Object.values(experiment.metrics)[0])}</div><ChevronRight /></button>) : <div className="empty-state"><History />Нет сохранённых экспериментов</div>}{activeExperiment && <div className="actual-reference"><div className="actual-reference-title"><Activity />Метрики: {experimentName(activeExperiment.experiment_id)}</div><div className="actual-reference-grid">{Object.entries(activeExperiment.metrics).map(([name, value]) => {return <div className="actual-reference-row" key={name}><span>{prettyName(name)}</span><strong className="actual-value">{formatValue(value, name)}</strong></div> })}</div></div>}</section><section className="panel support-card"><div className="card-heading"><div><h2>Надёжность прогноза</h2></div><Gauge /></div><div className={`support-level ${(supportDisplay?.level || prediction?.support?.level || 'unknown').toLowerCase()}`}>{prettyName(supportDisplay?.exact ? 'high' : supportDisplay?.level || prediction?.support?.level || 'pending')}</div>{(supportDisplay?.exact ? false : (supportDisplay?.level ?? prediction?.support?.level)?.toLowerCase() === 'low') && <div className="support-warning"><AlertTriangle/>Низкая надёжность: конфигурация за пределами области, подтверждённой экспериментами</div>}<div className="support-meta"><span>Ближайший эксперимент</span><strong>{experimentName(supportDisplay?.nearest_experiment_id || prediction?.support?.nearest_experiment_id || 'baseline')}</strong></div><div className="support-meta"><span>Расстояние</span><strong>{supportDisplay ? supportDisplay.distance.toLocaleString('ru-RU', { maximumFractionDigits: 3 }) : prediction?.support?.distance?.toLocaleString('ru-RU', { maximumFractionDigits: 3 }) || '—'}</strong></div></section></div>
          {/* Секция Grafana: iframe вынесен в отдельный компонент (см.
              components/GrafanaDashboard), URL — только из environment. */}
          <section className="grafana-section panel" id="summary"><div className="card-heading"><div><h2>Сводка сравнения моделей</h2></div><div className="grafana-label"><Activity />Grafana · онлайн</div></div><GrafanaDashboard theme={theme} url={GRAFANA_URL} paramName={selectedParam || model?.parameters[0]?.name} paramValue={selectedParam ? config[selectedParam] ?? null : model?.parameters[0] ? config[model.parameters[0].name] ?? null : null} metric={activeMetrics[0]?.name} /></section>
        </section>
      </div>
    </main>
  )
}
