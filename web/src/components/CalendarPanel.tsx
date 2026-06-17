import { useEffect, useState } from 'react'
import { getCalendar, type CalendarMonth } from '../api'

const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

function prevMonth(year: number, month: number): { year: number; month: number } {
  if (month === 1) return { year: year - 1, month: 12 }
  return { year, month: month - 1 }
}

function nextMonth(year: number, month: number): { year: number; month: number } {
  if (month === 12) return { year: year + 1, month: 1 }
  return { year, month: month + 1 }
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}

export default function CalendarPanel() {
  const today = new Date()
  const [year, setYear] = useState<number>(today.getFullYear())
  const [month, setMonth] = useState<number>(today.getMonth() + 1)
  const [data, setData] = useState<CalendarMonth | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setError(null)
    let cancelled = false
    getCalendar(year, month)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '캘린더 조회 실패')
          setData(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [year, month])

  function handlePrev() {
    const p = prevMonth(year, month)
    setYear(p.year)
    setMonth(p.month)
  }

  function handleNext() {
    const n = nextMonth(year, month)
    setYear(n.year)
    setMonth(n.month)
  }

  const todayStr = `${today.getFullYear()}-${pad2(today.getMonth() + 1)}-${pad2(today.getDate())}`

  // Leading blank cells: weekday index of the 1st of the month
  const leadingBlanks = new Date(year, month - 1, 1).getDay()

  return (
    <div className="card">
      <div className="card-title">거래 캘린더</div>

      <div className="cal-nav">
        <button onClick={handlePrev} aria-label="이전 달">◀</button>
        <span className="cal-nav-label">{year}년 {month}월</span>
        <button onClick={handleNext} aria-label="다음 달">▶</button>
      </div>

      <div className="calendar-grid">
        {WEEKDAYS.map((wd) => (
          <div key={wd} className="cal-weekday">{wd}</div>
        ))}

        {Array.from({ length: leadingBlanks }, (_, i) => (
          <div key={`blank-${i}`} className="cal-cell cal-cell-blank" />
        ))}

        {error == null && data == null && (
          <div className="cal-loading">불러오는 중…</div>
        )}

        {data != null &&
          data.days.map((day) => {
            const dayNum = Number(day.date.slice(8, 10))
            const isToday = day.date === todayStr

            let cellClass = 'cal-cell'
            if (!day.is_trading_day) {
              cellClass += ' cal-cell-holiday'
            } else {
              cellClass += ' cal-cell-open'
              if (day.is_half_day) {
                cellClass += ' cal-cell-half'
              }
            }
            if (isToday) {
              cellClass += ' cal-cell-today'
            }

            return (
              <div key={day.date} className={cellClass}>
                <span className="cal-day-num">{dayNum}</span>
                {day.is_half_day && day.close != null && (
                  <span className="cal-badge">조기 {day.close}</span>
                )}
              </div>
            )
          })}
      </div>

      {error != null && (
        <div className="cal-error">{error}</div>
      )}

      <div className="cal-legend">
        <span className="cal-legend-item">
          <span className="cal-legend-dot cal-legend-dot-open" />
          거래일
        </span>
        <span className="cal-legend-item">
          <span className="cal-legend-dot cal-legend-dot-holiday" />
          휴장
        </span>
        <span className="cal-legend-item">
          <span className="cal-legend-dot cal-legend-dot-half" />
          반장일
        </span>
        <span className="cal-legend-item">
          <span className="cal-legend-dot cal-legend-dot-today" />
          오늘
        </span>
      </div>
    </div>
  )
}
