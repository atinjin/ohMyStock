"""FastAPI 앱: 백테스트 엔진을 JSON으로 노출."""
import calendar as _pycal
import os
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
from ohmystock.core.broker.kis import KISBroker
from ohmystock.core.broker.toss import TossBroker


def _load_dotenv():
    """현재 디렉터리 .env 를 환경변수로 로드(있으면). python-dotenv 없으면 무시."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _read_only_broker(name: str, env=None):
    """읽기 전용 브로커 생성(주문·실제-돈 게이트 없음). 키는 env 폴백."""
    _load_dotenv()
    env = os.environ if env is None else env
    if name == "kis":
        paper = env.get("OHMYSTOCK_KIS_PAPER", "1").strip().lower() not in ("0", "false", "no")
        return KISBroker(paper=paper)
    if name == "toss":
        return TossBroker()
    raise ValueError(f"알 수 없는 브로커: {name}")


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


def create_app(adapter=None, paper_db="state/paper.db", broker_factory=None) -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter
    app.state.paper_db = paper_db
    app.state.calendar = None  # lazy: /api/calendar 첫 요청 때 생성
    app.state.broker_factory = broker_factory or _read_only_broker
    app.state.brokers = {}

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

    @app.get("/api/broker/account")
    def broker_account(broker: str):
        """선택 브로커의 실 계좌(읽기 전용): equity/cash + 보유."""
        if broker not in ("kis", "toss"):
            raise HTTPException(status_code=400, detail="broker는 kis|toss 이어야 합니다")
        try:
            b = app.state.brokers.get(broker)
            if b is None:
                b = app.state.broker_factory(broker)
                app.state.brokers[broker] = b
            acct = b.get_account()
            positions = b.get_positions()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        mode = "paper" if getattr(b, "paper", False) else "live"
        return {
            "broker": broker,
            "mode": mode,
            "equity": acct.equity,
            "cash": acct.cash,
            "positions": [{"symbol": s, "value": v} for s, v in positions.items()],
        }

    return app


app = create_app()
