# 거래일·장시간 캘린더 설계

**작성일:** 2026-06-17
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 § 첫 항목 (거래일·장시간 판정)

---

## 1. 목표

실계좌 스케줄러가 **"오늘 거래일인가, 언제 마감인가, 지금 장이 열렸나"**를 판단할 수 있도록, 미래 날짜까지 정확한 거래일·세션시각(반장일·DST 포함)을 제공하는 캘린더를 만든다.

확정된 결정:
- 휴장일·세션 판정: **`exchange_calendars` 라이브러리**(미국 XNYS, 한국 XKRX 지원). 정확·유지보수됨·미래 날짜 제공.
- 구조: `MarketCalendar` **인터페이스** + `ExchangeMarketCalendar`(거래소코드 래퍼) + `us_market_calendar()` 팩토리. 한국은 코드만 바꿔 확장.
- 캘린더는 내부에 "현재 시각"을 두지 않는다 → 모든 메서드가 날짜/시각 인자를 받아 **결정적**(시간 모킹 없이 테스트).

기존 `core/data/`의 데이터 유도 거래일(봉의 날짜)은 과거만 가능하므로 스케줄러엔 부적합 — 본 캘린더로 대체/보완.

---

## 2. 모듈 구조

```
ohmystock/core/calendar/
  __init__.py
  base.py        # MarketCalendar (Protocol)
  exchange.py    # ExchangeMarketCalendar + us_market_calendar()
```

의존성: `exchange_calendars` 1개 추가(`uv add exchange-calendars`). 내장 휴일 데이터라 런타임 네트워크 불필요.

---

## 3. MarketCalendar 인터페이스 (base.py)

```python
from datetime import date, datetime
from typing import Protocol


class MarketCalendar(Protocol):
    def is_trading_day(self, d: date) -> bool: ...
    def next_trading_day(self, d: date) -> date: ...        # d 다음 거래일(엄격히 이후)
    def previous_trading_day(self, d: date) -> date: ...     # d 직전 거래일(엄격히 이전)
    def session_times(self, d: date) -> tuple[datetime, datetime] | None: ...
    #   그 날 (개장, 마감) tz-aware(거래소 현지시각). 비거래일이면 None. 반장일 반영.
    def is_open(self, dt: datetime) -> bool: ...             # tz-aware 시각에 장이 열렸나
```

규약:
- 반환 datetime은 **tz-aware**(거래소 현지 타임존, 미국=America/New_York).
- `session_times`는 비거래일에 **None**(예외 아님) — 호출부 분기 용이. 반장일(early close, 예: 추수감사절 다음날 13:00 ET)을 정확히 반영.
- `is_open(dt)`: `dt`(tz-aware)가 해당 날짜 세션의 [개장, 마감] 범위 안인지. 비거래일/장외면 False. "지금 열렸나"는 호출부에서 `is_open(datetime.now(ZoneInfo("America/New_York")))`.
- `next/previous_trading_day`는 주말·휴일을 건너뛴다(엄격히 이후/이전, 같은 날 포함 안 함).

---

## 4. 구현 (exchange.py)

`ExchangeMarketCalendar(code: str)`가 `exchange_calendars.get_calendar(code)`를 래핑해 위 인터페이스로 변환. 라이브러리의 세션 판정·개폐장 시각(반장일 포함)을 사용하고, UTC 기준 시각을 거래소 타임존으로 변환해 반환한다.

```python
def us_market_calendar() -> ExchangeMarketCalendar:
    return ExchangeMarketCalendar("XNYS")
```

한국 확장: `ExchangeMarketCalendar("XKRX")`.

구현 세부(라이브러리 메서드 매핑)는 구현 계획에서 설치된 `exchange_calendars` 버전에 맞춰 확정한다(예: `is_session`, `date_to_session(direction=...)`, `session_open/close`, `is_open_on_minute`).

---

## 5. 에러 처리

- 라이브러리 지원 날짜 범위를 벗어난 요청: 원 예외를 그대로 전파(메시지에 날짜 포함). 일반적 운용 범위(현재~수년)에선 발생하지 않음.
- `session_times`의 비거래일은 정상 흐름(None).

---

## 6. 테스트 (오프라인, 결정적 — `exchange_calendars` 내장 데이터)

- **거래일**: 평일(예: 2024-07-03 수) True / 주말(2024-07-06 토·07-07 일) False / 고정휴일(2024-07-04 독립기념일) False.
- **반장일**: 2024-11-29(추수감사절 다음날) `session_times` 마감이 13:00 ET.
- **정상 마감일**: 2024-07-03(독립기념일 전날, 반장일)도 13:00 — 또는 일반일 16:00 ET 확인.
- **next/previous_trading_day**: 금요일(2024-07-05) 다음 거래일 = 월요일(2024-07-08); 7월 4일을 끼면 건너뜀; 같은 날은 포함 안 함.
- **is_open**: 개장 중(예: 2024-07-03 10:00 ET) True / 마감 후(2024-07-03 17:00 ET) False / 비거래일(2024-07-04 10:00 ET) False.
- 모든 테스트는 ZoneInfo 또는 pandas tz로 tz-aware 시각 구성.

---

## 7. 비범위

- 스케줄러 자체(다음 항목), 실계좌 주문, 한국(XKRX) 구현(인터페이스만 준비), 프리/애프터마켓 세션.
