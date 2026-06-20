import { useEffect, useState } from 'react'
import './App.css'
import {
  getLivePreview,
  getStrategies,
  runBacktest,
  type BacktestRequest,
  type LivePreview as LivePreviewData,
  type Report,
  type StrategyInfo,
} from './api'
import BacktestForm from './components/BacktestForm'
import CalendarPanel from './components/CalendarPanel'
import { ConceptProvider } from './components/ConceptModal'
import EquityChart from './components/EquityChart'
import LivePreview from './components/LivePreview'
import MetricsGrid from './components/MetricsGrid'
import PaperPanel from './components/PaperPanel'
import ScoreCard from './components/ScoreCard'
import SchedulerRunsPanel from './components/SchedulerRunsPanel'
import BrokerAccountPanel from './components/BrokerAccountPanel'

const currency = new Intl.NumberFormat('ko-KR', {
  style: 'currency',
  currency: 'KRW',
  maximumFractionDigits: 0,
})

function App() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [strategiesError, setStrategiesError] = useState<string | null>(null)
  const [report, setReport] = useState<Report | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<LivePreviewData | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [lastRequest, setLastRequest] = useState<BacktestRequest | null>(null)

  useEffect(() => {
    let cancelled = false
    getStrategies()
      .then((list) => {
        if (!cancelled) setStrategies(list)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setStrategiesError(
            err instanceof Error ? err.message : '전략 목록을 불러오지 못했습니다.',
          )
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleRun(req: BacktestRequest) {
    setLastRequest(req)
    setLoading(true)
    setError(null)
    try {
      const result = await runBacktest(req)
      setReport(result)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '백테스트 실행에 실패했습니다.')
      setReport(null)
    } finally {
      setLoading(false)
    }
  }

  async function handlePreview(req: BacktestRequest) {
    setLastRequest(req)
    setPreviewLoading(true)
    setPreviewError(null)
    try {
      const result = await getLivePreview(req)
      setPreview(result)
    } catch (err: unknown) {
      setPreviewError(
        err instanceof Error ? err.message : '미리보기 실행에 실패했습니다.',
      )
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  return (
    <ConceptProvider>
      <div className="app">
      <header className="app-header">
        <h1>OhMyStock — 전략 검증 대시보드</h1>
      </header>

      <div className="app-body">
        <aside className="app-sidebar">
          {strategiesError && (
            <div className="alert alert-error">{strategiesError}</div>
          )}
          <BacktestForm
            strategies={strategies}
            loading={loading || previewLoading}
            onRun={handleRun}
            onPreview={handlePreview}
          />
        </aside>

        <main className="app-main">
          {error && <div className="alert alert-error">{error}</div>}
          {previewError && (
            <div className="alert alert-error">{previewError}</div>
          )}

          {loading && (
            <div className="card placeholder">
              <div className="spinner" aria-hidden="true" />
              <p>백테스트를 실행하는 중입니다…</p>
            </div>
          )}

          {previewLoading && (
            <div className="card placeholder">
              <div className="spinner" aria-hidden="true" />
              <p>오늘 주문을 미리 계산하는 중입니다…</p>
            </div>
          )}

          {!previewLoading && preview && <LivePreview preview={preview} />}

          {!loading &&
            !previewLoading &&
            !report &&
            !preview &&
            !error &&
            !previewError && (
              <div className="card placeholder">
                <p>왼쪽에서 전략을 설정하고 백테스트를 실행하세요.</p>
              </div>
            )}

          {!loading && report && (
            <>
              <div className="card summary-card">
                <div className="summary-strategy">
                  {report.strategy}
                  <span className="summary-range">
                    {report.start} ~ {report.end}
                  </span>
                </div>
                <div className="summary-equity">
                  <span className="summary-equity-label">최종 자산</span>
                  <span className="summary-equity-value">
                    {currency.format(report.final_equity)}
                  </span>
                </div>
              </div>

              <EquityChart data={report.equity_curve} />
              <MetricsGrid metrics={report.metrics} />
              <ScoreCard
                validations={report.validations}
                dataValidation={report.data_validation}
              />
            </>
          )}

          <PaperPanel request={lastRequest} />
          <CalendarPanel />
          <SchedulerRunsPanel />
          <BrokerAccountPanel />
        </main>
      </div>
      </div>
    </ConceptProvider>
  )
}

export default App
