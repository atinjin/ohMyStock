"""견고성 검증(G3)이 공유하는 수익률 통계 헬퍼.

metrics.py의 Sharpe 규약(ddof=1, 연환산)과 일치시켜, 구간 슬라이스된
수익률 시리즈에서도 동일하게 계산하도록 한다.
"""
import numpy as np
import pandas as pd


def annualized_sharpe(returns, trading_days: int = 252,
                      risk_free_rate: float = 0.0) -> float:
    """연환산 Sharpe. 표본<2 또는 변동성 0이면 0.0."""
    r = pd.Series(returns).dropna()
    if len(r) < 2:
        return 0.0
    std = r.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    ann_ret = r.mean() * trading_days
    ann_vol = std * np.sqrt(trading_days)
    return float((ann_ret - risk_free_rate) / ann_vol)


def total_return(returns) -> float:
    """누적 총수익률(소수). 빈 입력이면 0.0."""
    r = pd.Series(returns).dropna()
    if len(r) == 0:
        return 0.0
    return float((1.0 + r).prod() - 1.0)


def max_drawdown_from_returns(returns) -> float:
    """수익률 시리즈로부터 최대 낙폭(양수). 빈 입력이면 0.0."""
    r = pd.Series(returns).dropna()
    if len(r) == 0:
        return 0.0
    eq = (1.0 + r).cumprod()
    peak = eq.cummax()
    dd = (eq - peak) / peak
    return float(-dd.min())
