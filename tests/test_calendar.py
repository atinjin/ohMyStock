def test_kr_market_calendar_is_xkrx():
    from ohmystock.core.calendar.exchange import kr_market_calendar
    cal = kr_market_calendar()
    # 2024-06-06 현충일(한국 공휴일) 휴장
    from datetime import date
    assert cal.is_trading_day(date(2024, 6, 6)) is False
    # 2024-06-05(수) 거래일
    assert cal.is_trading_day(date(2024, 6, 5)) is True
