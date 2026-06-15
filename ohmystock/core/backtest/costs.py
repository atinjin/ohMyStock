import pandas as pd
from ohmystock.config import Config


def turnover_series(weights: pd.DataFrame) -> pd.Series:
    """일별 회전율 = 비중 변화 절대합. 첫날은 진입(전일 0 가정)."""
    prev = weights.shift(1).fillna(0.0)
    return (weights - prev).abs().sum(axis=1)


def cost_series(weights: pd.DataFrame, config: Config) -> pd.Series:
    """일별 거래비용(자산 대비 비율)."""
    return turnover_series(weights) * config.cost_rate()
