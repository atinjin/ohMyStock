// Typed client for the OhMyStock backtest API.
// All requests go through the relative `/api/...` path (dev proxy -> :8000).

export type ParamValue = number | string | boolean

export interface StrategyInfo {
  name: string
  params: Record<string, ParamValue>
}

export interface BacktestRequest {
  strategy: string
  params: Record<string, ParamValue>
  symbols: string[]
  start: string
  end: string
  capital: number
}

export interface EquityPoint {
  date: string
  value: number
}

export interface Metric {
  key: string
  label: string
  value: number
  display: string
}

export type ValidationGroup = 'G2' | 'G3' | 'G4'

export interface Validation {
  group: ValidationGroup
  name: string
  value: number
  passed: boolean
  threshold: number | null
  message: string
}

export interface DataValidation {
  passed: boolean
  issues: string[]
  warnings: string[]
}

export interface Report {
  strategy: string
  symbols: string[]
  start: string
  end: string
  final_equity: number
  data_validation: DataValidation
  equity_curve: EquityPoint[]
  metrics: Metric[]
  validations: Validation[]
}

export interface Account {
  equity: number
  cash: number
}

export interface LiveOrder {
  symbol: string
  side: 'buy' | 'sell'
  notional: number
}

export interface LivePreview {
  strategy: string
  symbols: string[]
  account_before: Account
  account_after: Account
  orders: LiveOrder[]
  risk: {
    in_breach: boolean
    drawdown: number
  }
  prices: Record<string, number>
}

interface StrategiesResponse {
  strategies: StrategyInfo[]
}

async function parseError(res: Response): Promise<never> {
  let detail = `${res.status} ${res.statusText}`
  try {
    const body = (await res.json()) as { detail?: string }
    if (body && typeof body.detail === 'string') {
      detail = body.detail
    }
  } catch {
    // Non-JSON error body; fall back to status text.
  }
  throw new Error(detail)
}

export async function getStrategies(): Promise<StrategyInfo[]> {
  const res = await fetch('/api/strategies')
  if (!res.ok) {
    return parseError(res)
  }
  const data = (await res.json()) as StrategiesResponse
  return data.strategies
}

export async function runBacktest(req: BacktestRequest): Promise<Report> {
  const res = await fetch('/api/backtest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as Report
}

export async function getLivePreview(
  req: BacktestRequest,
): Promise<LivePreview> {
  const res = await fetch('/api/live/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as LivePreview
}

// Paper account types and client functions

export interface PaperPosition {
  symbol: string
  shares: number
}

export interface PaperState {
  exists: boolean
  config?: {
    strategy: string
    params: Record<string, ParamValue>
    symbols: string[]
    initial_capital: number
    start: string
    end: string
  }
  cursor_date?: string | null
  cash?: number
  equity?: number
  peak_equity?: number
  positions?: PaperPosition[]
  in_breach?: boolean
  drawdown?: number
}

export interface PaperTrade {
  date: string
  symbol: string
  side: string
  notional: number
  price: number
  shares: number
}

export interface PaperHistory {
  snapshots: { date: string; equity: number; cash: number }[]
  trades: PaperTrade[]
}

export function getPaperState(): Promise<PaperState> {
  return fetch('/api/paper/state').then((r) => r.json() as Promise<PaperState>)
}

export function getPaperHistory(): Promise<PaperHistory> {
  return fetch('/api/paper/history').then((r) => r.json() as Promise<PaperHistory>)
}

export async function initPaper(req: BacktestRequest): Promise<PaperState> {
  const r = await fetch('/api/paper/init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!r.ok) {
    const body = (await r.json()) as { detail?: string }
    throw new Error(body.detail ?? '초기화 실패')
  }
  return r.json() as Promise<PaperState>
}

export async function stepPaper(): Promise<{ done?: boolean; date?: string }> {
  const r = await fetch('/api/paper/step', { method: 'POST' })
  if (!r.ok) {
    const body = (await r.json()) as { detail?: string }
    throw new Error(body.detail ?? '스텝 실패')
  }
  return r.json() as Promise<{ done?: boolean; date?: string }>
}

export async function runPaper(body: {
  steps?: number
  to?: string
}): Promise<{ results: unknown[] }> {
  const r = await fetch('/api/paper/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!r.ok) {
    const errBody = (await r.json()) as { detail?: string }
    throw new Error(errBody.detail ?? '실행 실패')
  }
  return r.json() as Promise<{ results: unknown[] }>
}

// Calendar types and client functions

export interface CalendarDay {
  date: string
  is_trading_day: boolean
  open: string | null
  close: string | null
  is_half_day: boolean
}

export interface CalendarMonth {
  year: number
  month: number
  days: CalendarDay[]
}

export async function getCalendar(year: number, month: number): Promise<CalendarMonth> {
  const r = await fetch(`/api/calendar?year=${year}&month=${month}`)
  if (!r.ok) throw new Error((await r.json() as { detail?: string }).detail ?? '캘린더 조회 실패')
  return r.json() as Promise<CalendarMonth>
}

// Scheduler run history types and client functions

export interface SchedulerRun {
  id: number
  ts: string
  status: string
  reason: string
  target: string | null
  steps: number
  equity: number | null
  attempts: number
  error: string | null
}

export async function getSchedulerRuns(limit = 20): Promise<SchedulerRun[]> {
  const r = await fetch(`/api/scheduler/runs?limit=${limit}`)
  if (!r.ok) throw new Error((await r.json() as { detail?: string }).detail ?? '실행 내역 조회 실패')
  return (await r.json() as { runs: SchedulerRun[] }).runs
}

// 실 계좌 현황 (읽기 전용)

export interface BrokerAccount {
  broker: string
  mode: string
  equity: number
  cash: number
  positions: { symbol: string; value: number }[]
}

export async function getBrokerAccount(
  broker: 'kis' | 'toss',
): Promise<BrokerAccount> {
  const res = await fetch('/api/broker/account?broker=' + broker)
  if (!res.ok) {
    return parseError(res)
  }
  return (await res.json()) as BrokerAccount
}
