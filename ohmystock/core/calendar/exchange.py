from datetime import date, datetime

import pandas as pd
import exchange_calendars as xcals


class ExchangeMarketCalendar:
    """exchange_calendars 래퍼. MarketCalendar 인터페이스 구현."""

    def __init__(self, code: str = "XNYS"):
        self._cal = xcals.get_calendar(code)
        self._tz = self._cal.tz

    def _in_bounds(self, ts: pd.Timestamp) -> bool:
        return self._cal.first_session <= ts <= self._cal.last_session

    def is_trading_day(self, d: date) -> bool:
        ts = pd.Timestamp(d)
        if not self._in_bounds(ts):
            return False
        return bool(self._cal.is_session(ts))

    def next_trading_day(self, d: date) -> date:
        ts = pd.Timestamp(d)
        if self._cal.is_session(ts):
            return self._cal.next_session(ts).date()
        return self._cal.date_to_session(ts, direction="next").date()

    def previous_trading_day(self, d: date) -> date:
        ts = pd.Timestamp(d)
        if self._cal.is_session(ts):
            return self._cal.previous_session(ts).date()
        return self._cal.date_to_session(ts, direction="previous").date()

    def session_times(self, d: date) -> tuple[datetime, datetime] | None:
        ts = pd.Timestamp(d)
        if not self._in_bounds(ts) or not self._cal.is_session(ts):
            return None
        open_local = self._cal.session_open(ts).tz_convert(self._tz)
        close_local = self._cal.session_close(ts).tz_convert(self._tz)
        return (open_local.to_pydatetime(), close_local.to_pydatetime())

    def is_open(self, dt: datetime) -> bool:
        ts = pd.Timestamp(dt)
        if ts.tz is None:
            raise ValueError("tz-aware datetime이 필요합니다")
        d = ts.tz_convert(self._tz).date()
        if not (self._cal.first_session.date() <= d <= self._cal.last_session.date()):
            return False
        try:
            return bool(self._cal.is_open_on_minute(ts.floor("min")))
        except Exception:
            return False


def us_market_calendar() -> ExchangeMarketCalendar:
    """미국(NYSE/XNYS) 캘린더."""
    return ExchangeMarketCalendar("XNYS")


def kr_market_calendar() -> ExchangeMarketCalendar:
    """한국(KRX/XKRX) 캘린더."""
    return ExchangeMarketCalendar("XKRX")
