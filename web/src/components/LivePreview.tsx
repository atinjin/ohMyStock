import type { LivePreview as LivePreviewData } from '../api'

interface Props {
  preview: LivePreviewData
}

const usd = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const percent = new Intl.NumberFormat('ko-KR', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export default function LivePreview({ preview }: Props) {
  const { orders, risk, account_before } = preview
  const inBreach = risk.in_breach

  return (
    <div className="card">
      <div className="scorecard-header">
        <h2 className="card-title">오늘 주문 미리보기 (페이퍼 — 실주문 없음)</h2>
        <span
          className={`live-badge ${inBreach ? 'live-badge-breach' : 'live-badge-ok'}`}
        >
          {inBreach ? 'MDD 한도 위반 · 신규진입 차단' : '리스크 정상'}
          <span className="live-badge-dd">
            DD {percent.format(risk.drawdown)}
          </span>
        </span>
      </div>

      {orders.length === 0 ? (
        <div className="live-empty">오늘 제출할 주문 없음 (이미 목표 비중)</div>
      ) : (
        <table className="orders-table">
          <thead>
            <tr>
              <th>종목</th>
              <th>구분</th>
              <th className="orders-amount">금액</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order, i) => (
              <tr key={`${order.symbol}-${i}`}>
                <td className="orders-symbol">{order.symbol}</td>
                <td>
                  <span
                    className={`order-side ${
                      order.side === 'buy' ? 'order-buy' : 'order-sell'
                    }`}
                  >
                    {order.side === 'buy' ? 'BUY' : 'SELL'}
                  </span>
                </td>
                <td className="orders-amount">{usd.format(order.notional)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="live-account">
        <span className="live-account-label">자금</span>
        <span className="live-account-value">
          {usd.format(account_before.equity)}
        </span>
      </div>
    </div>
  )
}
