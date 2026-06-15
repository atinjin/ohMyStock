import { useEffect, useMemo, useState } from 'react'
import type {
  BacktestRequest,
  ParamValue,
  StrategyInfo,
} from '../api'

interface Props {
  strategies: StrategyInfo[]
  loading: boolean
  onRun: (req: BacktestRequest) => void
  onPreview?: (req: BacktestRequest) => void
}

const DEFAULT_SYMBOLS = 'AAPL,MSFT,GOOGL,AMZN,META'
const DEFAULT_START = '2020-01-01'
const DEFAULT_END = '2024-01-01'
const DEFAULT_CAPITAL = 5_000_000

function coerceParam(original: ParamValue, raw: string): ParamValue {
  if (typeof original === 'number') {
    const n = Number(raw)
    return Number.isNaN(n) ? original : n
  }
  if (typeof original === 'boolean') {
    return raw === 'true'
  }
  return raw
}

export default function BacktestForm({
  strategies,
  loading,
  onRun,
  onPreview,
}: Props) {
  const [strategyName, setStrategyName] = useState('')
  const [params, setParams] = useState<Record<string, ParamValue>>({})
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS)
  const [start, setStart] = useState(DEFAULT_START)
  const [end, setEnd] = useState(DEFAULT_END)
  const [capital, setCapital] = useState(DEFAULT_CAPITAL)

  const selected = useMemo(
    () => strategies.find((s) => s.name === strategyName),
    [strategies, strategyName],
  )

  // Pick the first strategy once they load, and reset params to its defaults
  // whenever the selected strategy changes.
  useEffect(() => {
    if (strategies.length === 0) return
    const current =
      strategies.find((s) => s.name === strategyName) ?? strategies[0]
    if (current.name !== strategyName) {
      setStrategyName(current.name)
    }
    setParams({ ...current.params })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategies, strategyName])

  function updateParam(key: string, raw: string) {
    setParams((prev) => ({
      ...prev,
      [key]: coerceParam(prev[key], raw),
    }))
  }

  function buildRequest(): BacktestRequest | null {
    if (!strategyName) return null
    const parsedSymbols = symbols
      .split(',')
      .map((s) => s.trim())
      .filter((s) => s.length > 0)
    return {
      strategy: strategyName,
      params,
      symbols: parsedSymbols,
      start,
      end,
      capital,
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const req = buildRequest()
    if (req) onRun(req)
  }

  function handlePreview() {
    if (!onPreview) return
    const req = buildRequest()
    if (req) onPreview(req)
  }

  return (
    <form className="card form" onSubmit={handleSubmit}>
      <h2 className="card-title">백테스트 설정</h2>

      <label className="field">
        <span className="field-label">전략</span>
        <select
          value={strategyName}
          onChange={(e) => setStrategyName(e.target.value)}
          disabled={loading || strategies.length === 0}
        >
          {strategies.length === 0 && <option value="">불러오는 중…</option>}
          {strategies.map((s) => (
            <option key={s.name} value={s.name}>
              {s.name}
            </option>
          ))}
        </select>
      </label>

      {selected && Object.keys(params).length > 0 && (
        <fieldset className="field-group" disabled={loading}>
          <legend className="field-label">파라미터</legend>
          <div className="param-grid">
            {Object.entries(params).map(([key, value]) => (
              <label key={key} className="field">
                <span className="field-sublabel">{key}</span>
                {typeof value === 'boolean' ? (
                  <select
                    value={String(value)}
                    onChange={(e) => updateParam(key, e.target.value)}
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    type={typeof value === 'number' ? 'number' : 'text'}
                    value={String(value)}
                    onChange={(e) => updateParam(key, e.target.value)}
                  />
                )}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <label className="field">
        <span className="field-label">종목 (쉼표 구분)</span>
        <input
          type="text"
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
          placeholder="AAPL, MSFT"
          disabled={loading}
        />
      </label>

      <div className="field-row">
        <label className="field">
          <span className="field-label">시작일</span>
          <input
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            disabled={loading}
          />
        </label>
        <label className="field">
          <span className="field-label">종료일</span>
          <input
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            disabled={loading}
          />
        </label>
      </div>

      <label className="field">
        <span className="field-label">초기 자본</span>
        <input
          type="number"
          value={capital}
          min={0}
          step={100000}
          onChange={(e) => setCapital(Number(e.target.value))}
          disabled={loading}
        />
      </label>

      <button type="submit" className="run-btn" disabled={loading || !strategyName}>
        {loading ? '실행 중…' : '백테스트 실행'}
      </button>

      {onPreview && (
        <button
          type="button"
          className="preview-btn"
          onClick={handlePreview}
          disabled={loading || !strategyName}
        >
          오늘 주문 미리보기
        </button>
      )}
    </form>
  )
}
