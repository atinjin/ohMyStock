# 스케줄러 진입점 설계 (cron 래퍼)

**작성일:** 2026-06-17
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 § 두 번째 항목 (스케줄러 진입점)

---

## 1. 목표

매 거래일 **장 마감 후 1회**, 페이퍼 계좌의 리밸런싱을 자동 전진시키는 **멱등 CLI 진입점**을 만든다. 상주 데몬 없이, 외부 cron 또는 `/schedule`(cloud agent)이 주기적으로 호출하면 "지금 돌릴 때인가"를 스스로 판정해 due일 때만 최신 거래일까지 따라잡는다.

확정된 결정:
- 방식: **cron 래퍼**("due면 1회 실행" CLI). APScheduler 상주 데몬은 비범위(나중에 이 위에 얇게 얹을 수 있음).
- 전진량: **최신 거래일까지 따라잡기**(`PaperService.run(to=target)`). 호출이 밀려도 한 번에 최신화. 멱등.
- 대상: **페이퍼 계좌**(`PaperService`). 실계좌(Alpaca/KIS)는 키가 필요하므로 다음 로드맵 항목.
- 결정적: `now`·`MarketCalendar`·`PaperService`를 주입 → 시계 모킹 없이 테스트.

재사용: `core/calendar/exchange.py::us_market_calendar()`(`is_trading_day`/`previous_trading_day`/`session_times`), `paper/service.py::PaperService`(`get_state`/`run`), `paper/sqlite_store.py`, `core/data/yfinance_adapter.py`, `config.py`.

---

## 2. 모듈 구조

```
ohmystock/scheduler.py
  compute_target_date(calendar, now: datetime) -> date | None
  run_once(service, calendar, now: datetime) -> dict
  run_cli(argv=None, *, service=None, calendar=None, now=None) -> dict
  main() -> None        # python -m ohmystock.scheduler run-once
```

단일 모듈(얇은 오케스트레이터). 기존 코어를 호출만 한다.

---

## 3. due 판정 — `compute_target_date(calendar, now)`

`now`(tz-aware)를 시장 타임존으로 보고, **마감이 완료된 가장 최근 거래일**(date)을 반환:

```
et_now = now (이미 ET 기준으로 들어온다고 가정; 호출부가 datetime.now(ET) 전달)
today = et_now.date()
if calendar.is_trading_day(today):
    times = calendar.session_times(today)   # (open, close) tz-aware
    if et_now >= close:        # 오늘 마감 완료
        return today
    return calendar.previous_trading_day(today)   # 아직 마감 전 -> 직전 거래일
else:
    return calendar.previous_trading_day(today)   # 휴장/주말 -> 직전 거래일
```

이 `target`까지의 일봉은 완결 데이터라 안전하게 체결 가능(마감 전 부분 데이터 유입 방지).

---

## 4. 오케스트레이션 — `run_once(service, calendar, now)`

```
state = service.get_state()
if not state["exists"]:
    return {"ran": False, "reason": "계좌 없음"}
target = compute_target_date(calendar, now)
cursor = state["cursor_date"]              # "YYYY-MM-DD" 또는 None
if target is None:
    return {"ran": False, "reason": "거래일 없음"}
if cursor is not None and cursor >= target.isoformat():
    return {"ran": False, "reason": "최신", "cursor": cursor, "target": target.isoformat()}
results = service.run(to=target.isoformat())   # 밀린 거래일을 최신까지 따라잡기
new_state = service.get_state()
return {
    "ran": len(results) > 0,
    "reason": "전진" if results else "데이터 없음",
    "target": target.isoformat(),
    "steps": len(results),
    "cursor": new_state["cursor_date"],
    "equity": new_state["equity"],
}
```

- `PaperService.run(to=...)`는 커서를 **앞으로만** 전진하고, 데이터가 target보다 짧으면 `engine.step`이 데이터 끝에서 멈춘다 → target이 데이터 범위를 넘어도 안전(따라잡을 수 있는 데까지).
- **멱등성**: 같은 날 마감 후 또 호출해도 커서가 이미 target 이상 → `{ran: False, "최신"}`.
- 마감 전·휴장엔 target이 직전 거래일이라 오늘을 건드리지 않음.

---

## 5. CLI — `python -m ohmystock.scheduler run-once`

- `run-once [--db state/paper.db]`: `service = PaperService(SqlitePaperStore(db), YFinanceAdapter(...), Config())`, `calendar = us_market_calendar()`, `now = datetime.now(ZoneInfo("America/New_York"))` → `run_once` 실행 후 결과 dict를 한 줄로 print(cron 로그용). 종료코드 0.
- 테스트를 위해 `run_cli`는 `service`/`calendar`/`now`를 주입받을 수 있게(미주입 시 실제 객체 생성).

---

## 6. 에러 처리

- 계좌 미생성: `{ran: False, "계좌 없음"}` (예외 아님 — cron이 조용히 넘어감).
- 데이터 fetch 실패: `service.run` 내부 예외 전파(어떤 종목·기간인지 메시지 포함). cron 로그에 남음.
- `now`가 tz-naive면 호출부 책임(ET tz-aware 전달). `run_once`는 받은 now를 그대로 사용.

---

## 7. 테스트 (결정적·오프라인)

`compute_target_date` (실제 `us_market_calendar()` + 주입 now):
- 거래일 마감 후: now=2024-07-02 17:00 ET(마감 16:00) → 2024-07-02
- 거래일 마감 전: now=2024-07-02 12:00 ET → 직전거래일 2024-07-01
- 반장일 마감 후: now=2024-07-03 14:00 ET(마감 13:00) → 2024-07-03
- 주말: now=2024-07-06(토) 10:00 ET → 2024-07-05
- 휴일: now=2024-07-04 10:00 ET → 2024-07-03

`run_once` (FakeAdapter 합성 일봉 + 임시 SqlitePaperStore + 주입 now):
- 계좌 init 후 first run → 커서가 최신(데이터 끝/target)까지 전진, ran=True, steps>0
- 2회차 호출 → ran=False("최신"), steps 없음(멱등)
- 계좌 미생성 → ran=False("계좌 없음")

`run_cli`: 주입(service/calendar/now)으로 `run-once` 실행 → 결과 dict 반환·print 확인.

모든 테스트 네트워크 불필요.

---

## 8. 비범위

- APScheduler 상주 데몬, 실계좌(Alpaca/KIS) 타깃, 알림, cron/cloud 등록 자동화(문서로만 안내). 한국 시장.
