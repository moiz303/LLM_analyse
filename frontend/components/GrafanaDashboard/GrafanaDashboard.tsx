const GRAFANA_ORIGIN_DEFAULT = 'http://localhost:3000'

type Props = {
  /* Базовый URL дашборда из env (может содержать orgId/kiosk). */
  url?: string
  /* Имя выбранного ползунка — уходит в дашборд как var-param_name. */
  paramName?: string
  /* Текущее значение выбранного ползунка — var-param_value. */
  paramValue?: number | null
  /* Метрика для оси Y — var-metric_choice. */
  metric?: string
}

/* Отправляет Grafana standard-событие refresh-dashboard. */
export function requestGrafanaRefresh(iframeUrl?: string) {
  try {
    const origin = new URL(iframeUrl || GRAFANA_ORIGIN_DEFAULT).origin
    window.postMessage({ type: 'refresh-dashboard' }, origin)
  } catch {
    /* некорректный URL — просто не обновляем */
  }
}

function splitBase(url: string) {
  try {
    const parsed = new URL(url, window.location.origin)
    const search = new URLSearchParams(parsed.search)
    search.delete('var-param_name')
    search.delete('var-metric_choice')
    parsed.search = search.toString()
    return parsed.toString().replace(/[?&]$/, '')
  } catch {
    return url
  }
}

export default function GrafanaDashboard({ url, paramName, metric }: Props) {
  const raw = url || process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_URL || process.env.VITE_GRAFANA_DASHBOARD_URL || ''

  // Если Grafana недоступна/URL не задан — показываем заглушку: отказ Grafana не должен ломать prediction UI.
  if (!raw) {
    return (
      <div className="grafana-placeholder">
        <span>
          Задайте <code>NEXT_PUBLIC_GRAFANA_DASHBOARD_URL</code>, чтобы подключить дашборд.
        </span>
      </div>
    )
  }

  const base = splitBase(raw)
  const params = new URLSearchParams()
  if (paramName) params.set('var-param_name', paramName)
  if (metric) params.set('var-metric_choice', metric)

  const extra = params.toString()
  const src = extra ? `${base}${base.includes('?') ? '&' : '?'}${extra}` : base

  return (
    <iframe
      // key меняет ссылку целиком — при переключении параметра Grafana перечитывает дашборд с новыми var-* значениями.
      key={src}
      src={src}
      title="Grafana dashboard"
      className="grafana-frame"
      width="100%"
      height={700}
      frameBorder="0"
      loading="lazy"
    />
  )
}
