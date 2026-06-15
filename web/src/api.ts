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
