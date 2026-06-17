"""거래일 스케줄러 진입점 (cron 래퍼).

매 거래일 장 마감 후 페이퍼 계좌를 최신 거래일까지 전진시킨다. 멱등.
"""
import argparse
from datetime import date, datetime
from zoneinfo import ZoneInfo

from ohmystock.config import Config
from ohmystock.core.calendar.exchange import us_market_calendar
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore

DEFAULT_DB = "state/paper.db"

_ET = ZoneInfo("America/New_York")


def compute_target_date(calendar, now: datetime) -> date | None:
    """마감이 완료된 가장 최근 거래일. now는 tz-aware여야 하며 ET로 정규화한다."""
    if now.tzinfo is None:
        raise ValueError("now는 tz-aware여야 합니다")
    now = now.astimezone(_ET)
    today = now.date()
    if calendar.is_trading_day(today):
        times = calendar.session_times(today)
        if times is not None:
            _open, close = times
            if now >= close:
                return today
        return calendar.previous_trading_day(today)
    return calendar.previous_trading_day(today)


def run_once(service, calendar, now: datetime) -> dict:
    """due면 페이퍼 계좌를 최신 거래일까지 전진. 멱등(커서는 앞으로만 이동)."""
    state = service.get_state()
    if not state.get("exists"):
        return {"ran": False, "reason": "계좌 없음"}

    target = compute_target_date(calendar, now)
    if target is None:
        return {"ran": False, "reason": "거래일 없음"}

    target_iso = target.isoformat()
    cursor = state.get("cursor_date")
    if cursor is not None and cursor >= target_iso:
        return {"ran": False, "reason": "최신", "cursor": cursor, "target": target_iso}

    results = service.run(to=target_iso)
    new_state = service.get_state()
    return {
        "ran": len(results) > 0,
        "reason": "전진" if results else "데이터 없음",
        "target": target_iso,
        "steps": len(results),
        "cursor": new_state.get("cursor_date"),
        "equity": new_state.get("equity"),
    }


def run_cli(argv=None, *, service=None, calendar=None, now=None) -> dict:
    parser = argparse.ArgumentParser(prog="ohmystock.scheduler")
    parser.add_argument("--db", default=DEFAULT_DB)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run-once")
    args = parser.parse_args(argv)

    if service is None:
        service = PaperService(
            SqlitePaperStore(args.db),
            YFinanceAdapter(cache=ParquetCache(".cache")),
            Config(),
        )
    if calendar is None:
        calendar = us_market_calendar()
    if now is None:
        now = datetime.now(_ET)

    result = run_once(service, calendar, now)
    print(result)
    return result


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
