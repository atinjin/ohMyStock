from datetime import date, datetime
from zoneinfo import ZoneInfo
from ohmystock.core.calendar.exchange import us_market_calendar

ET = ZoneInfo("America/New_York")


def test_is_trading_day():
    cal = us_market_calendar()
    assert cal.is_trading_day(date(2024, 7, 3)) is True    # 수요일 거래일
    assert cal.is_trading_day(date(2024, 7, 4)) is False   # 독립기념일(휴장)
    assert cal.is_trading_day(date(2024, 7, 6)) is False   # 토요일


def test_next_previous_trading_day_strict_and_skip():
    cal = us_market_calendar()
    assert cal.next_trading_day(date(2024, 7, 5)) == date(2024, 7, 8)
    assert cal.next_trading_day(date(2024, 7, 3)) == date(2024, 7, 8)
    assert cal.next_trading_day(date(2024, 7, 6)) == date(2024, 7, 8)
    assert cal.previous_trading_day(date(2024, 7, 8)) == date(2024, 7, 5)
    assert cal.previous_trading_day(date(2024, 7, 6)) == date(2024, 7, 5)


def test_session_times_full_half_and_none():
    cal = us_market_calendar()
    full = cal.session_times(date(2024, 7, 2))
    assert full is not None
    o, c = full
    assert (o.hour, o.minute) == (9, 30)
    assert (c.hour, c.minute) == (16, 0)

    half = cal.session_times(date(2024, 7, 3))
    assert half is not None
    _, hc = half
    assert (hc.hour, hc.minute) == (13, 0)

    assert cal.session_times(date(2024, 7, 4)) is None


def test_is_open():
    cal = us_market_calendar()
    assert cal.is_open(datetime(2024, 7, 3, 10, 0, tzinfo=ET)) is True
    assert cal.is_open(datetime(2024, 7, 3, 15, 0, tzinfo=ET)) is False
    assert cal.is_open(datetime(2024, 7, 4, 10, 0, tzinfo=ET)) is False
    assert cal.is_open(datetime(2024, 7, 6, 10, 0, tzinfo=ET)) is False
