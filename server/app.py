"""FastAPI 앱: 백테스트 엔진을 JSON으로 노출."""
import calendar as _pycal
from datetime import date

from fastapi import FastAPI, HTTPException
from ohmystock.core.calendar.exchange import us_market_calendar
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock import report
from ohmystock.live import live_preview
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore
from ohmystock.scheduler_store import SqliteSchedulerStore


class BacktestRequest(BaseModel):
    strategy: str
    params: dict = {}
    symbols: list[str]
    start: str
    end: str
    capital: float = 5_000_000


class RunRequest(BaseModel):
    steps: int | None = None
    to: str | None = None


# 전략별 기본 파라미터 (GET /api/strategies 응답용)
_STRATEGY_DEFAULTS = {
    "MACrossover": {"short": 20, "long": 60},
    "Momentum": {"lookback": 90, "top_k": 3},
}


def create_app(adapter=None, paper_db="state/paper.db") -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter
    app.state.paper_db = paper_db
    app.state.calendar = None  # lazy: /api/calendar 첫 요청 때 생성

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/strategies")
    def strategies():
        return {
            "strategies": [
                {"name": name, "params": params}
                for name, params in _STRATEGY_DEFAULTS.items()
            ]
        }

    @app.post("/api/backtest")
    def run_backtest(req: BacktestRequest):
        try:
            strategy = report.build_strategy(req.strategy, req.params)
            start = date.fromisoformat(req.start)
            end = date.fromisoformat(req.end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        config = Config(initial_capital=req.capital)
        return report.full_report(
            symbols=req.symbols, start=start, end=end,
            adapter=app.state.adapter, strategy=strategy, config=config)

    @app.post("/api/live/preview")
    def live_preview_endpoint(req: BacktestRequest):
        """오늘자 목표 리밸런싱 주문 미리보기(페이퍼 — 실주문 없음)."""
        try:
            strategy = report.build_strategy(req.strategy, req.params)
            start = date.fromisoformat(req.start)
            end = date.fromisoformat(req.end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        config = Config(initial_capital=req.capital)
        return live_preview(
            symbols=req.symbols, start=start, end=end,
            adapter=app.state.adapter, strategy=strategy, config=config)

    def _paper_service() -> PaperService:
        return PaperService(SqlitePaperStore(app.state.paper_db), app.state.adapter, Config())

    @app.post("/api/paper/init")
    def paper_init(req: BacktestRequest):
        try:
            date.fromisoformat(req.start)
            date.fromisoformat(req.end)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        svc = _paper_service()
        svc.init_account(req.strategy, req.params, req.symbols, req.capital,
                         req.start, req.end)
        return svc.get_state()

    @app.post("/api/paper/step")
    def paper_step():
        try:
            res = _paper_service().step()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return res if res is not None else {"done": True}

    @app.post("/api/paper/run")
    def paper_run(req: RunRequest):
        try:
            results = _paper_service().run(steps=req.steps, to=req.to)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"results": results}

    @app.get("/api/paper/state")
    def paper_state():
        return _paper_service().get_state()

    @app.get("/api/paper/history")
    def paper_history():
        return _paper_service().get_history()

    def _market_calendar():
        if app.state.calendar is None:
            app.state.calendar = us_market_calendar()
        return app.state.calendar

    @app.get("/api/calendar")
    def market_calendar(year: int, month: int):
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="month은 1~12 이어야 합니다")
        cal = _market_calendar()
        n_days = _pycal.monthrange(year, month)[1]
        days = []
        for day in range(1, n_days + 1):
            d = date(year, month, day)
            times = cal.session_times(d)
            if times is None:
                days.append({
                    "date": d.isoformat(), "is_trading_day": False,
                    "open": None, "close": None, "is_half_day": False,
                })
            else:
                open_dt, close_dt = times
                days.append({
                    "date": d.isoformat(), "is_trading_day": True,
                    "open": open_dt.strftime("%H:%M"),
                    "close": close_dt.strftime("%H:%M"),
                    "is_half_day": close_dt.hour < 16,
                })
        return {"year": year, "month": month, "days": days}

    @app.get("/api/scheduler/runs")
    def scheduler_runs(limit: int = 20):
        limit = max(1, min(limit, 200))
        store = SqliteSchedulerStore(app.state.paper_db)
        return {"runs": store.recent_runs(limit)}

    return app


app = create_app()
