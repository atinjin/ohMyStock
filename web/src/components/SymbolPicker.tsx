import { useMemo, useRef, useState } from 'react'
import { SYMBOLS, lookupName } from '../symbols'
import type { SymbolInfo } from '../symbols'
import { getRecentSymbols } from '../history'

interface Props {
  value: string[]
  onChange: (symbols: string[]) => void
  disabled?: boolean
}

const MAX_SUGGESTIONS = 8

export default function SymbolPicker({ value, onChange, disabled }: Props) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = useMemo(() => new Set(value), [value])

  // Catalog matches for the current query (symbol prefix or name substring).
  const suggestions = useMemo<SymbolInfo[]>(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    const out: SymbolInfo[] = []
    for (const info of SYMBOLS) {
      if (selected.has(info.symbol)) continue
      if (
        info.symbol.toLowerCase().startsWith(q) ||
        info.name.toLowerCase().includes(q)
      ) {
        out.push(info)
        if (out.length >= MAX_SUGGESTIONS) break
      }
    }
    return out
  }, [query, selected])

  // Recent symbols shown when the input is empty + focused.
  const recent = useMemo<SymbolInfo[]>(() => {
    if (query.trim()) return []
    const out: SymbolInfo[] = []
    for (const symbol of getRecentSymbols()) {
      if (selected.has(symbol)) continue
      out.push({ symbol, name: lookupName(symbol) ?? '' })
      if (out.length >= MAX_SUGGESTIONS) break
    }
    return out
  }, [query, selected])

  // Catalog picks shown on focus when the input is empty, so the dropdown is
  // useful immediately even with no history. Fills the slots left by `recent`.
  const popular = useMemo<SymbolInfo[]>(() => {
    if (query.trim()) return []
    const recentSet = new Set(recent.map((r) => r.symbol))
    const out: SymbolInfo[] = []
    for (const info of SYMBOLS) {
      if (selected.has(info.symbol) || recentSet.has(info.symbol)) continue
      out.push(info)
      if (recent.length + out.length >= MAX_SUGGESTIONS) break
    }
    return out
  }, [query, selected, recent])

  function addSymbol(raw: string) {
    const symbol = raw.trim().toUpperCase()
    if (!symbol || selected.has(symbol)) return
    onChange([...value, symbol])
    setQuery('')
    inputRef.current?.focus()
  }

  function removeSymbol(symbol: string) {
    if (disabled) return
    onChange(value.filter((s) => s !== symbol))
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter') {
      e.preventDefault()
      if (query.trim()) addSymbol(query)
    } else if (e.key === ',') {
      e.preventDefault()
      if (query.trim()) addSymbol(query)
    } else if (e.key === 'Backspace' && !query && value.length > 0) {
      removeSymbol(value[value.length - 1])
    }
  }

  const showDropdown =
    focused &&
    (query.trim()
      ? suggestions.length > 0
      : recent.length > 0 || popular.length > 0)

  const renderItem = (info: SymbolInfo) => (
    <li key={info.symbol}>
      <button
        type="button"
        className="symbol-suggest-item"
        // onMouseDown fires before input blur, keeping focus stable.
        onMouseDown={(e) => {
          e.preventDefault()
          addSymbol(info.symbol)
        }}
      >
        <span className="symbol-suggest-code">{info.symbol}</span>
        {info.name && (
          <span className="symbol-suggest-name">{info.name}</span>
        )}
      </button>
    </li>
  )

  return (
    <div className="symbol-picker">
      {value.length > 0 && (
        <div className="symbol-chips">
          {value.map((symbol) => {
            const name = lookupName(symbol)
            return (
              <span
                key={symbol}
                className="symbol-chip"
                title={name ?? symbol}
              >
                <span className="symbol-chip-code">{symbol}</span>
                {name && <span className="symbol-chip-name">{name}</span>}
                {!disabled && (
                  <button
                    type="button"
                    className="symbol-chip-remove"
                    aria-label={`${symbol} 제거`}
                    onClick={() => removeSymbol(symbol)}
                  >
                    ×
                  </button>
                )}
              </span>
            )
          })}
        </div>
      )}

      <input
        ref={inputRef}
        type="text"
        className="symbol-input"
        aria-label="종목 검색"
        value={query}
        placeholder="종목 검색 (예: AAPL, Apple)"
        disabled={disabled}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />

      {showDropdown && (
        <ul className="symbol-suggest">
          {query.trim() ? (
            suggestions.map(renderItem)
          ) : (
            <>
              {recent.length > 0 && (
                <>
                  <li className="symbol-suggest-head">최근 사용</li>
                  {recent.map(renderItem)}
                </>
              )}
              {popular.length > 0 && (
                <>
                  <li className="symbol-suggest-head">추천 종목</li>
                  {popular.map(renderItem)}
                </>
              )}
            </>
          )}
        </ul>
      )}
    </div>
  )
}
