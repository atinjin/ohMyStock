from fastapi.testclient import TestClient
from server.app import create_app


class FakeAdapter:
    def get_daily_bars(self, symbols, start, end):
        return {}


def _client():
    return TestClient(create_app(adapter=FakeAdapter()))


def test_calendar_month():
    c = _client()
    r = c.get("/api/calendar?year=2024&month=7")
    assert r.status_code == 200
    data = r.json()
    assert data["year"] == 2024 and data["month"] == 7
    days = {d["date"]: d for d in data["days"]}
    assert len(days) == 31
    assert days["2024-07-04"]["is_trading_day"] is False
    assert days["2024-07-03"]["is_trading_day"] is True
    assert days["2024-07-03"]["close"] == "13:00"
    assert days["2024-07-03"]["is_half_day"] is True
    assert days["2024-07-02"]["close"] == "16:00"
    assert days["2024-07-02"]["is_half_day"] is False


def test_calendar_bad_month():
    assert _client().get("/api/calendar?year=2024&month=13").status_code == 400
