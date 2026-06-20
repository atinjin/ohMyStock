import { useCallback, useEffect, useState } from 'react'
import { getMarketOverview, type MarketItem, type MarketOverview } from '../api'

const POLL_MS = 30000
const UP = '#e5484d' // 상승 빨강(한국식)
const DOWN = '#3b82f6' // 하락 파랑

function sparkPath(values: number[], w = 96, h = 28): string {
  if (values.length < 2) return ''
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w
      const y = h - ((v - min) / span) * h
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

function fmtNum(n: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(n)
}

function MarketCard({ item }: { item: MarketItem }) {
  const up = item.change >= 0
  const color = up ? UP : DOWN
  const sign = up ? '+' : ''
  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 8, padding: '10px 12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <span style={{ fontWeight: 600 }}>{item.label}</span>
        {item.badge && (
          <span style={{ fontSize: 11, color: 'var(--text-dim)', border: '1px solid var(--border)', borderRadius: 4, padding: '0 5px' }}>
            {item.badge}
          </span>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <svg width={96} height={28} style={{ flexShrink: 0 }}>
          <path d={sparkPath(item.sparkline)} fill="none" stroke={color} strokeWidth={1.5} />
        </svg>
        <div>
          <div style={{ fontSize: 18, fontVariantNumeric: 'tabular-nums' }}>{fmtNum(item.value)}</div>
          <div style={{ fontSize: 13, color, fontVariantNumeric: 'tabular-nums' }}>
            {sign}
            {fmtNum(item.change)} ({sign}
            {item.change_pct.toFixed(2)}%)
          </div>
        </div>
      </div>
    </div>
  )
}

function statusDot(open: boolean) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: open ? '#22c55e' : 'var(--text-dim)' }} />
      {open ? '열림' : '닫힘'}
    </span>
  )
}

export default function MarketOverviewPanel() {
  const [data, setData] = useState<MarketOverview | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await getMarketOverview())
      setError(null)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '시장 개요 조회 실패')
    }
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
        <h2 className="card-title" style={{ margin: 0 }}>시장 개요</h2>
        {data && (
          <div style={{ display: 'flex', gap: 16, fontSize: 13, color: 'var(--text-dim)' }}>
            <span>국내 장 {statusDot(data.markets.kr.open)}</span>
            <span>해외 장 {statusDot(data.markets.us.open)}</span>
          </div>
        )}
        <button onClick={load} style={{ marginLeft: 'auto' }}>새로고침</button>
      </div>

      {error ? (
        <p style={{ color: 'var(--fail)' }}>{error}</p>
      ) : data === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginTop: 12 }}>
          {data.items.map((it) => (
            <MarketCard key={it.key} item={it} />
          ))}
        </div>
      )}
    </div>
  )
}
