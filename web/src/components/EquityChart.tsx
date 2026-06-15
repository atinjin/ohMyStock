import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { EquityPoint } from '../api'

interface Props {
  data: EquityPoint[]
}

const compact = new Intl.NumberFormat('ko-KR', {
  notation: 'compact',
  maximumFractionDigits: 1,
})

const full = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 0 })

function formatAxisValue(value: number): string {
  return `₩${compact.format(value)}`
}

export default function EquityChart({ data }: Props) {
  return (
    <div className="card chart-card">
      <h2 className="card-title">자산 곡선</h2>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={320}>
          <LineChart
            data={data}
            margin={{ top: 8, right: 16, left: 8, bottom: 8 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="var(--grid)" />
            <XAxis
              dataKey="date"
              tick={{ fill: 'var(--text-dim)', fontSize: 12 }}
              minTickGap={32}
            />
            <YAxis
              tickFormatter={formatAxisValue}
              tick={{ fill: 'var(--text-dim)', fontSize: 12 }}
              width={72}
              domain={['auto', 'auto']}
            />
            <Tooltip
              formatter={(value) => [`₩${full.format(Number(value))}`, '자산']}
              labelStyle={{ color: 'var(--text)' }}
              contentStyle={{
                background: 'var(--surface-2)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                color: 'var(--text)',
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              stroke="var(--accent)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
