"""전략을 데이터에 대해 백테스트하는 얇은 래퍼.

과최적화 검증 등에서 파라미터를 바꿔가며 재실행할 때 사용한다.
"""
from ohmystock.core.backtest.engine import run_backtest


def backtest(strategy, bars, config):
    """generate_signals → run_backtest 묶음. BacktestResult 반환."""
    signals = strategy.generate_signals(bars)
    return run_backtest(bars, signals, config)
