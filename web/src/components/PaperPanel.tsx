import { useEffect, useState } from 'react'
import {
  getFx,
  getPaperState,
  getPaperHistory,
  initPaper,
  stepPaper,
  runPaper,
  type BacktestRequest,
  type PaperState,
  type PaperHistory,
} from '../api'
import EquityChart from './EquityChart'
import { usd, approxKrw } from '../format'

interface Props {
  request: BacktestRequest | null
}

export default function PaperPanel({ request }: Props) {
  const [state, setState] = useState<PaperState | null>(null)
  const [history, setHistory] = useState<PaperHistory | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fxRate, setFxRate] = useState<number | null>(null)

  useEffect(() => {
    const load = () => getFx().then((f) => setFxRate(f.rate)).catch(() => setFxRate(null))
    load()
    const id = setInterval(load, 300_000) // 5분마다 갱신(백엔드 TTL과 일치)
    return () => clearInterval(id)
  }, [])

  async function refresh() {
    try {
      const [s, h] = await Promise.all([getPaperState(), getPaperHistory()])
      setState(s)
      setHistory(h)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '불러오기 실패')
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function handleInit() {
    if (!request) return
    setLoading(true)
    setError(null)
    try {
      await initPaper(request)
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '초기화 실패')
    } finally {
      setLoading(false)
    }
  }

  async function handleStep() {
    setLoading(true)
    setError(null)
    try {
      await stepPaper()
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '스텝 실패')
    } finally {
      setLoading(false)
    }
  }

  async function handleRun() {
    setLoading(true)
    setError(null)
    try {
      await runPaper({})
      await refresh()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '실행 실패')
    } finally {
      setLoading(false)
    }
  }

  const inBreach = state?.in_breach ?? false
  const drawdown = state?.drawdown ?? 0

  return (
    <div className="card">
      <h2 className="card-title">페이퍼 계좌</h2>

      {state === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : state.exists === false ? (
        <div>
          <p style={{ color: 'var(--text-dim)', marginBottom: 12 }}>
            페이퍼 계좌가 없습니다.
          </p>
          <button
            className="run-btn"
            disabled={request === null || loading}
            onClick={() => void handleInit()}
          >
            현재 설정으로 초기화
          </button>
        </div>
      ) : (
        <>
          {/* Config summary */}
          <p className="paper-config">
            전략 {state.config?.strategy ?? '-'} · 종목{' '}
            {state.config?.symbols.join(', ') ?? '-'} · {state.config?.start ?? '-'}~
            {state.config?.end ?? '-'} · 커서{' '}
            {state.cursor_date ?? '시작 전'}
          </p>

          {/* Metric cards */}
          <div className="metrics-grid" style={{ marginBottom: 16 }}>
            <div className="metric-card">
              <div className="metric-label">현재 자산</div>
              <div className="metric-value">
                {usd(state.equity ?? 0)}
                <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>{approxKrw(state.equity ?? 0, fxRate)}</span>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-label">현금</div>
              <div className="metric-value">{usd(state.cash ?? 0)}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">고점</div>
              <div className="metric-value">{usd(state.peak_equity ?? 0)}</div>
            </div>
          </div>

          {/* Risk badge */}
          <div style={{ marginBottom: 16 }}>
            <span
              className={`live-badge ${inBreach ? 'live-badge-breach' : 'live-badge-ok'}`}
            >
              {inBreach ? 'MDD 한도 위반' : '리스크 정상'}
              <span className="live-badge-dd">
                낙폭 {(drawdown * 100).toFixed(1)}%
              </span>
            </span>
          </div>

          {/* Equity curve */}
          {history && history.snapshots.length >= 1 ? (
            <EquityChart
              data={history.snapshots.map((s) => ({
                date: s.date,
                value: s.equity,
              }))}
            />
          ) : (
            <p style={{ color: 'var(--text-dim)', marginBottom: 16 }}>
              스텝을 진행하면 자산곡선이 표시됩니다
            </p>
          )}

          {/* Positions table */}
          {state.positions && state.positions.length > 0 ? (
            <div style={{ marginBottom: 16 }}>
              <h3
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text-dim)',
                  marginBottom: 8,
                  textTransform: 'uppercase',
                  letterSpacing: '0.4px',
                }}
              >
                보유 포지션
              </h3>
              <table className="orders-table">
                <thead>
                  <tr>
                    <th>종목</th>
                    <th className="orders-amount">보유수량</th>
                  </tr>
                </thead>
                <tbody>
                  {state.positions.map((pos) => (
                    <tr key={pos.symbol}>
                      <td className="orders-symbol">{pos.symbol}</td>
                      <td className="orders-amount">{pos.shares.toFixed(4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p style={{ color: 'var(--text-dim)', marginBottom: 16 }}>
              보유 없음
            </p>
          )}

          {/* Trades table */}
          {history && history.trades.length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <h3
                style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--text-dim)',
                  marginBottom: 8,
                  textTransform: 'uppercase',
                  letterSpacing: '0.4px',
                }}
              >
                최근 거래
              </h3>
              <table className="orders-table">
                <thead>
                  <tr>
                    <th>날짜</th>
                    <th>종목</th>
                    <th>구분</th>
                    <th className="orders-amount">금액</th>
                  </tr>
                </thead>
                <tbody>
                  {history.trades
                    .slice(-20)
                    .reverse()
                    .map((trade, i) => (
                      <tr key={`${trade.date}-${trade.symbol}-${i}`}>
                        <td>{trade.date}</td>
                        <td className="orders-symbol">{trade.symbol}</td>
                        <td>
                          <span
                            className={`order-side ${
                              trade.side.toUpperCase() === 'BUY'
                                ? 'order-buy'
                                : 'order-sell'
                            }`}
                          >
                            {trade.side.toUpperCase() === 'BUY' ? 'BUY' : 'SELL'}
                          </span>
                        </td>
                        <td className="orders-amount">
                          {usd(trade.notional)}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Action buttons */}
          <div className="paper-actions">
            <button
              className="preview-btn"
              disabled={loading}
              onClick={() => void handleStep()}
            >
              한 스텝
            </button>
            <button
              className="preview-btn"
              disabled={loading}
              onClick={() => void handleRun()}
            >
              끝까지 빠르게
            </button>
            <button
              className="run-btn"
              disabled={request === null || loading}
              onClick={() => void handleInit()}
            >
              초기화
            </button>
          </div>
        </>
      )}

      {error && (
        <p style={{ marginTop: 10, fontSize: 13, color: 'var(--fail)' }}>
          {error}
        </p>
      )}
    </div>
  )
}
