from datetime import date

from ohmystock.config import Config
from ohmystock.paper.account import PaperAccount
from ohmystock.paper import engine


class PaperService:
    """페이퍼 계좌 운용 묶음: store + 데이터 어댑터 + 엔진."""

    def __init__(self, store, adapter, config=None):
        self.store = store
        self.adapter = adapter
        self.config = config or Config()

    def init_account(self, strategy, params, symbols, capital, start, end) -> PaperAccount:
        account = PaperAccount(
            strategy=strategy, params=dict(params or {}), symbols=list(symbols),
            initial_capital=capital, start_date=start, end_date=end,
            cursor_date=None, cash=capital, peak_equity=capital)
        self.store.initialize(account)
        return account

    def _bars(self, account: PaperAccount) -> dict:
        return self.adapter.get_daily_bars(
            account.symbols,
            date.fromisoformat(account.start_date),
            date.fromisoformat(account.end_date))

    def step(self):
        account = self.store.load_account()
        if account is None:
            raise ValueError("페이퍼 계좌가 없습니다. 먼저 init 하세요.")
        return engine.step(account, self.store, self._bars(account), self.config)

    def run(self, steps=None, to=None) -> list[dict]:
        results: list[dict] = []
        while True:
            account = self.store.load_account()
            if account is None:
                raise ValueError("페이퍼 계좌가 없습니다. 먼저 init 하세요.")
            res = engine.step(account, self.store, self._bars(account), self.config)
            if res is None:
                break
            results.append(res)
            if steps is not None and len(results) >= steps:
                break
            if to is not None and res["date"] >= to:
                break
        return results

    def get_state(self) -> dict:
        account = self.store.load_account()
        if account is None:
            return {"exists": False}
        positions = self.store.load_positions()
        snaps = self.store.snapshots()
        equity = snaps[-1]["equity"] if snaps else account.cash
        drawdown = (
            0.0 if account.peak_equity <= 0
            else max(0.0, (account.peak_equity - equity) / account.peak_equity)
        )
        return {
            "exists": True,
            "config": {
                "strategy": account.strategy, "params": account.params,
                "symbols": account.symbols, "initial_capital": account.initial_capital,
                "start": account.start_date, "end": account.end_date,
            },
            "cursor_date": account.cursor_date,
            "cash": account.cash, "equity": equity, "peak_equity": account.peak_equity,
            "positions": [{"symbol": s, "shares": q} for s, q in positions.items()],
            "in_breach": bool(drawdown > self.config.mdd_limit),
            "drawdown": float(drawdown),
        }

    def get_history(self) -> dict:
        return {"snapshots": self.store.snapshots(), "trades": self.store.trades()}
