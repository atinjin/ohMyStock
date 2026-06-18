import { useEffect, useState } from 'react'
import { getSchedulerRuns, type SchedulerRun } from '../api'

export default function SchedulerRunsPanel() {
  const [runs, setRuns] = useState<SchedulerRun[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getSchedulerRuns(20)
      .then((data) => setRuns(data))
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : '실행 내역 조회 실패')
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function statusClass(status: string): string {
    if (status === 'ok') return 'run-ok'
    if (status === 'failed') return 'run-failed'
    return 'run-skipped'
  }

  function truncate(text: string, max = 60): string {
    return text.length > max ? text.slice(0, max) + '…' : text
  }

  return (
    <div className="card">
      <h2 className="card-title">스케줄러 실행 내역</h2>

      {error ? (
        <p style={{ color: 'var(--fail)' }}>{error}</p>
      ) : runs === null ? (
        <p style={{ color: 'var(--text-dim)' }}>불러오는 중…</p>
      ) : runs.length === 0 ? (
        <p style={{ color: 'var(--text-dim)' }}>실행 기록 없음</p>
      ) : (
        <table className="orders-table">
          <thead>
            <tr>
              <th>시각</th>
              <th>상태</th>
              <th>target</th>
              <th>steps</th>
              <th>시도</th>
              <th>사유</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td style={{ fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap' }}>
                  {run.ts.replace('T', ' ').slice(0, 16)}
                </td>
                <td>
                  <span className={statusClass(run.status)}>{run.status}</span>
                </td>
                <td>{run.target ?? '-'}</td>
                <td>{run.steps}</td>
                <td>{run.attempts}</td>
                <td style={{ color: 'var(--text-dim)', fontSize: 13 }}>
                  {truncate(run.error ?? run.reason)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
