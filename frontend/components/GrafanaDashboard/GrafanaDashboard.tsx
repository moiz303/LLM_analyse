'use client'

// Grafana — только визуальный слой над данными, которые пишет backend.
// Frontend не использует Grafana API, не подключается к InfluxDB и не хранит
// credentials (см. documentations/frontend_TASKA.md, разделы 18–20).
//
// URL дашборда приходит из environment: NEXT_PUBLIC_GRAFANA_DASHBOARD_URL
// (в Vite-схеме из таска — VITE_GRAFANA_DASHBOARD_URL); в качестве fallback
// используется стандартный адрес провижиненного дашборда model-comparison.
// Значение прокидывается из page.tsx, чтобы источник env-переменных был один.
const GRAFANA_DASHBOARD_DEFAULT = 'http://localhost:3000/d/model-comparison/model-comparison?orgId=1&kiosk'

type Props = { url?: string }

export default function GrafanaDashboard({ url }: Props) {
  const src = url || process.env.NEXT_PUBLIC_GRAFANA_DASHBOARD_URL || process.env.VITE_GRAFANA_DASHBOARD_URL || GRAFANA_DASHBOARD_DEFAULT

  // Если Grafana недоступна/URL не задан — показываем заглушку: отказ Grafana
  // не должен ломать prediction UI (раздел 24 таска).
  if (!src) {
    return (
      <div className="grafana-placeholder">
        <span>
          Set <code>NEXT_PUBLIC_GRAFANA_DASHBOARD_URL</code> to connect the dashboard.
        </span>
      </div>
    )
  }

  return (
    <iframe
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
