// 금액 포맷 헬퍼.

/** 천 단위 콤마 (예: 5000000 -> "5,000,000"). 음수/소수는 버림. */
export function withCommas(n: number): string {
  return Math.floor(Math.max(0, n)).toLocaleString('en-US')
}

/** 원화 금액을 한글 단위로 읽어준다 (예: 500000000 -> "5억원", 5000000 -> "500만원"). */
export function koreanAmount(n: number): string {
  const v = Math.floor(n)
  if (!Number.isFinite(v) || v <= 0) return '0원'
  const units: { value: number; label: string }[] = [
    { value: 1_0000_0000_0000, label: '조' },
    { value: 1_0000_0000, label: '억' },
    { value: 1_0000, label: '만' },
    { value: 1, label: '' },
  ]
  let rem = v
  const parts: string[] = []
  for (const { value, label } of units) {
    const g = Math.floor(rem / value)
    if (g > 0) {
      parts.push(`${g.toLocaleString('en-US')}${label}`)
      rem -= g * value
    }
  }
  return parts.join(' ') + '원'
}

/** USD 통화 포맷 (예: 10000 -> "$10,000"). */
export function usd(n: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 0,
  }).format(n)
}

/** USD 금액의 원화 환산 참고 (예: " ≈ 1,531만원"). rate 없으면 빈 문자열. */
export function approxKrw(usdAmount: number, rate: number | null): string {
  if (!rate || !Number.isFinite(usdAmount)) return ''
  return ' ≈ ' + koreanAmount(usdAmount * rate)
}
