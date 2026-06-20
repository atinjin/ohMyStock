import { useCallback, useEffect, useState, type CSSProperties } from 'react'
import { getBrokerAccount, type BrokerAccount } from '../api'

const BROKERS: { key: 'kis' | 'toss'; label: string }[] = [
  { key: 'kis', label: 'KIS (모의)' },
  { key: 'toss', label: 'TOSS' },
]
const POLL_MS = 30000

function formatter(broker: string): Intl.NumberFormat {
  const usd = broker === 'toss'
  return new Intl.NumberFormat(usd ? 'en-US' : 'ko-KR', {
    style: 'currency',
    currency: usd ? 'USD' : 'KRW',
    maximumFractionDigits: usd ? 2 : 0,
  })
}

export default function BrokerAccountPanel() {
  const [broker, setBroker] = useState<'kis' | 'toss'>('kis')
  const [data, setData] = useState<BrokerAccount | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async (b: 'kis' | 'toss') => {
    setLoading(true)
    setError(null)
    try {
      setData(await getBrokerAccount(b))
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '계좌 조회 실패')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load(broker)
    const id = setInterval(() => load(broker), POLL_MS)
    return () => clearInterval(id)
  }, [broker, load])

  const fmt = formatter(broker)

  function tabStyle(active: boolean): CSSProperties {
    return {
      padding: '4px 10px',
      borderRadius: 4,
      cursor: 'pointer',
      border: '1px solid var(--border, #ccc)',
      background: active ? 'var(--accent, #2a6)' : 'transparent',
      color: active ? '#fff' : 'inherit',
    }
  }

  return (
    <div className="card">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <h2 className="card-title" style={{ margin: 0 }}>실 계좌 현황</h2>
        <span
          style={{
            fontSize: 12,
            color: 'var(--text-dim)',
            border: '1px solid var(--text-dim)',
            borderRadius: 4,
            padding: '1px 6px',
          }}
        >
          읽기 전용 · 실 계좌
        </span>
        <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
          {BROKERS.map((b) => (
            <button key={b.key} onClick={() => setBroker(b.key)} style={tabStyle(broker === b.key)}>
              {b.label}
            </button>
          ))}
          <button onClick={() => load(broker)} disabled={loading}>
            새로고침
          </button>
        </div>
      </div>

      {error ? (
        <p style={{ color: 'var(--fail)' }}>{error}</p>
      ) : data === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 24, margin: '12px 0' }}>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>
                총 자산 (equity) · {data.mode === 'paper' ? '모의' : '실전'}
              </div>
              <div style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>
                {fmt.format(data.equity)}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-dim)' }}>예수금 (cash)</div>
              <div style={{ fontSize: 22, fontVariantNumeric: 'tabular-nums' }}>
                {fmt.format(data.cash)}
              </div>
            </div>
          </div>
          {data.positions.length === 0 ? (
            <p style={{ color: 'var(--text-dim)' }}>보유 종목 없음</p>
          ) : (
            <table className="orders-table">
              <thead>
                <tr>
                  <th>종목</th>
                  <th>평가금액</th>
                </tr>
              </thead>
              <tbody>
                {data.positions.map((p) => (
                  <tr key={p.symbol}>
                    <td>{p.symbol}</td>
                    <td style={{ fontVariantNumeric: 'tabular-nums' }}>{fmt.format(p.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  )
}
