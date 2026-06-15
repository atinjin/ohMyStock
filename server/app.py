"""FastAPI 앱: 백테스트 엔진을 JSON으로 노출."""
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock import report
from ohmystock.live import live_preview


class BacktestRequest(BaseModel):
    strategy: str
    params: dict = {}
    symbols: list[str]
    start: str
    end: str
    capital: float = 5_000_000


# 전략별 기본 파라미터 (GET /api/strategies 응답용)
_STRATEGY_DEFAULTS = {
    "MACrossover": {"short": 20, "long": 60},
    "Momentum": {"lookback": 90, "top_k": 3},
}


def create_app(adapter=None) -> FastAPI:
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))

    app = FastAPI(title="OhMyStock API")
    app.state.adapter = adapter

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

    return app


app = create_app()
