import numpy as np
from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult


def max_drawdown(result: BacktestResult) -> float:
    """누적 고점 대비 최대 낙폭(양수). ⑩"""
    eq = result.equity_curve
    peak = eq.cummax()
    dd = (eq - peak) / peak
    return float(-dd.min())


def _initial_equity(result: BacktestResult) -> float:
    """returns[0] 적용 전 초기 자산가치를 역산한다."""
    eq0 = result.equity_curve.iloc[0]
    r0 = result.returns.iloc[0]
    return float(eq0 / (1.0 + r0))


def _cagr(result: BacktestResult, cfg: Config) -> float:
    eq = result.equity_curve
    n = len(result.returns)
    if n == 0:
        return 0.0
    initial = _initial_equity(result)
    return float((eq.iloc[-1] / initial) ** (cfg.trading_days / n) - 1)


def sharpe_ratio(result: BacktestResult, cfg: Config) -> float:
    """(연환산수익 - 무위험) / 연환산변동성. ⑪"""
    r = result.returns
    std = r.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    ann_ret = r.mean() * cfg.trading_days
    ann_vol = std * np.sqrt(cfg.trading_days)
    return float((ann_ret - cfg.risk_free_rate) / ann_vol)


def sortino_ratio(result: BacktestResult, cfg: Config) -> float:
    """하방변동성만 사용. ⑫"""
    r = result.returns
    downside = r.clip(upper=0.0)
    dstd = np.sqrt((downside ** 2).mean())
    if dstd == 0 or np.isnan(dstd):
        return 0.0
    ann_ret = r.mean() * cfg.trading_days
    ann_dvol = dstd * np.sqrt(cfg.trading_days)
    return float((ann_ret - cfg.risk_free_rate) / ann_dvol)


def calmar_ratio(result: BacktestResult, cfg: Config) -> float:
    """연환산수익(CAGR) / MDD. ⑬"""
    mdd = max_drawdown(result)
    if mdd == 0:
        return 0.0
    return _cagr(result, cfg) / mdd


def profit_factor(result: BacktestResult) -> float:
    """총이익 / |총손실|. ⑭"""
    pnl = result.trades["pnl"] if "pnl" in result.trades else []
    if len(pnl) == 0:
        return 0.0
    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


def recovery_factor(result: BacktestResult) -> float:
    """순수익률 / MDD. ⑮"""
    mdd = max_drawdown(result)
    if mdd == 0:
        return 0.0
    initial = _initial_equity(result)
    total_ret = result.equity_curve.iloc[-1] / initial - 1
    return float(total_ret / mdd)
