# 스케줄러 재시도·백오프 + 실행 로그/상태 기록 설계

**작성일:** 2026-06-19
**상태:** 설계 확정
**로드맵:** 실계좌 스케줄링 § "실패 재시도·백오프 + 실행 로그/상태 기록"
**선행:** 스케줄러 진입점(`ohmystock/scheduler.py`: `compute_target_date`/`run_once`/CLI) 완료

---

## 1. 목표

스케줄러가 **일시적 실패(데이터 fetch 등)를 지수 백오프로 재시도**하고, **각 실행 결과를 SQLite에 영속 기록**해 "오늘 돌았나 / 실패했나 / 마지막 성공 언제"를 CLI·API·대시보드로 볼 수 있게 한다.

확정된 결정:
- 기록 위치: **`paper.db`의 `scheduler_runs` 테이블** (스케줄러 전용 store로 분리).
- 재시도: run 중 **예외 시 최대 3회·지수 백오프(5s→10s→20s)**, 전부 설정 가능. "계좌 없음" 등 정상 스킵·결과는 재시도 안 함.
- 가시성: CLI(`history`/`last-run`) + API(`GET /api/scheduler/runs`) + 대시보드 패널.
- 결정적 테스트: `now`·`sleep` 주입.

재사용: `ohmystock/scheduler.py::run_once`(멱등 단일 시도 — 변경 없이 재시도로 감쌈), `SqlitePaperStore` 패턴, `server/app.py`, 기존 대시보드 패널 스타일.

---

## 2. 저장소 (`ohmystock/scheduler_store.py`)

```python
class SchedulerStore(Protocol):
    def record_run(self, *, ts: str, status: str, reason: str,
                   target: str | None, steps: int, equity: float | None,
                   attempts: int, error: str | None) -> None: ...
    def recent_runs(self, limit: int = 20) -> list[dict]: ...
    def last_run(self) -> dict | None: ...
    def last_success(self) -> dict | None: ...   # status="ok"
```

`SqliteSchedulerStore(db_path)`가 구현. 테이블(없으면 생성):
```sql
CREATE TABLE IF NOT EXISTS scheduler_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, status TEXT, reason TEXT, target TEXT,
  steps INTEGER, equity REAL, attempts INTEGER, error TEXT
);
```
- `status` ∈ `"ok"`(전진) · `"skipped"`(계좌없음/최신/데이터없음/거래일없음) · `"failed"`(재시도 소진).
- `recent_runs`/`last_run`: `ORDER BY id DESC`. 각 행은 dict(컬럼명 키).
- `SqlitePaperStore`와 같은 db 파일을 공유하지만 테이블이 달라 충돌 없음. 커넥션은 `contextlib.closing` + `with conn`.

---

## 3. 재시도·백오프 + 기록 (`ohmystock/scheduler.py::run_scheduled`)

`run_once`(기존, 단일 시도, 멱등)는 그대로. 위에 오케스트레이터 추가:

```python
import time

def run_scheduled(service, calendar, store, now, *,
                  max_attempts: int = 3, base_delay: float = 5.0,
                  factor: float = 2.0, sleep=time.sleep) -> dict:
    attempt = 0
    last_error = None
    result = None
    while attempt < max_attempts:
        attempt += 1
        try:
            result = run_once(service, calendar, now)
            last_error = None
            break
        except Exception as exc:          # 일시적 실패 -> 백오프 후 재시도
            last_error = exc
            if attempt < max_attempts:
                sleep(base_delay * (factor ** (attempt - 1)))

    ts = now.isoformat()
    if last_error is not None:
        store.record_run(ts=ts, status="failed", reason=str(last_error)[:200],
                         target=None, steps=0, equity=None,
                         attempts=attempt, error=repr(last_error))
        raise last_error                  # cron이 비-0 종료로 인지
    status = "ok" if result["ran"] else "skipped"
    store.record_run(ts=ts, status=status, reason=result["reason"],
                     target=result.get("target"), steps=result.get("steps", 0),
                     equity=result.get("equity"), attempts=attempt, error=None)
    return {**result, "status": status, "attempts": attempt}
```

- `run_once`가 멱등(커서 전진만)이라 재시도가 안전(부분 전진 후 재시도해도 새 커서에서 이어감).
- 백오프 지연: `5 → 10 → 20`(기본). `sleep` 주입으로 테스트는 실제 대기 없음.
- `now`(ET tz-aware)의 `isoformat()`을 기록 시각으로.

---

## 4. CLI (`ohmystock/scheduler.py`)

- `run-once`: 이제 `SqliteSchedulerStore(db)`를 만들어 `run_scheduled`로 실행(재시도+기록). 결과 한 줄 출력.
- `history [--limit N]`: `store.recent_runs(N)`를 표 형태로 출력.
- `last-run`: `store.last_run()` + `store.last_success()` 출력("마지막 실행 / 마지막 성공").
- 주입(`service`/`calendar`/`store`/`now`/`sleep`) 가능하게 유지.

---

## 5. API (`server/app.py`)

- `GET /api/scheduler/runs?limit=20` → `{"runs": [ {id, ts, status, reason, target, steps, equity, attempts, error}, ... ]}`. `SqliteSchedulerStore(app.state.paper_db)` lazy 생성. `limit`는 1~200으로 제한, 벗어나면 클램프.

---

## 6. 대시보드 (`web/src/components/SchedulerRunsPanel.tsx`)

- "스케줄러 실행 내역" 카드. `GET /api/scheduler/runs`로 최근 실행을 표로:
  시각 / 상태(색: ok=녹색·skipped=중립·failed=빨강) / target / steps / 시도 / 에러(있으면).
- 비어 있으면 "실행 기록 없음". 다크 테마·기존 표 스타일 재사용. `App.tsx`에 마운트.

---

## 7. 에러 처리

- 재시도 대상 = `run_once` 중 발생한 예외(주로 `service.run`의 데이터 실패). "계좌 없음"·"최신"·"데이터 없음"은 정상 결과(dict)라 재시도 안 함 → status `skipped`.
- 전부 실패: `failed` 기록 후 원 예외 재발생(cron 로그·종료코드).
- 기록 자체 실패(DB 오류)는 드물지만 발생 시 전파(스케줄러가 조용히 성공으로 위장하지 않게).

---

## 8. 테스트 (결정적·오프라인)

- `SqliteSchedulerStore`(임시 db): record_run → recent_runs/last_run/last_success 왕복, 순서(id DESC), 빈 상태 None.
- `run_scheduled`(가짜 service/calendar/store + 주입 now·sleep):
  - 성공 전진 → status `ok`, attempts 1, record 1행
  - 스킵(계좌 없음) → status `skipped`, attempts 1
  - 재시도 후 성공: service.run이 N-1회 예외 후 성공 → attempts N, sleep N-1회 호출, status ok
  - 전부 실패: service.run 항상 예외 → status `failed` 기록 + 원 예외 raise, sleep (max-1)회
- CLI: `run-once`(기록됨)·`history`·`last-run` 주입 실행 출력 확인.
- API: TestClient + 임시 paper_db → `/api/scheduler/runs` 형태.
- 프론트: `npm run build`.

---

## 9. 비범위

- APScheduler 상주 데몬, 실계좌 타깃, 알림(다음 항목), cron/cloud 등록 자동화.
