// Recently-used symbol history, persisted in localStorage.
// All access is guarded for SSR / private-mode / quota safety.

const STORAGE_KEY = 'ohmystock.recentSymbols'
const MAX_RECENT = 20

export function getRecentSymbols(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((s): s is string => typeof s === 'string')
  } catch {
    return []
  }
}

export function addRecentSymbols(symbols: string[]): void {
  const incoming = symbols
    .map((s) => s.trim().toUpperCase())
    .filter((s) => s.length > 0)
  if (incoming.length === 0) return

  // Most-recent-first, de-duplicated, capped.
  const merged: string[] = []
  for (const symbol of [...incoming, ...getRecentSymbols()]) {
    if (!merged.includes(symbol)) merged.push(symbol)
    if (merged.length >= MAX_RECENT) break
  }

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(merged))
  } catch {
    // Storage unavailable or over quota; history is best-effort only.
  }
}
