import type { Metric } from '../api'

interface Props {
  metrics: Metric[]
}

export default function MetricsGrid({ metrics }: Props) {
  return (
    <div className="card">
      <h2 className="card-title">핵심 지표</h2>
      <div className="metrics-grid">
        {metrics.map((m) => (
          <div key={m.key} className="metric-card">
            <div className="metric-label">{m.label}</div>
            <div className="metric-value">{m.display}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
