"""구조화된 JSON 직렬화 가능 리포트. CLI/API 공통 단일 진실원천(SSOT)."""
from ohmystock.core.data.validation import validate_bars
from ohmystock.core.backtest.runner import backtest
from ohmystock.core.validation import metrics as M
from ohmystock.core.validation.kelly import kelly_criterion
from ohmystock.core.validation.ruin import ruin_probability
from ohmystock.core.validation.capacity import capacity_analysis
from ohmystock.core.validation.out_of_sample import out_of_sample
from ohmystock.core.validation.walk_forward import walk_forward
from ohmystock.core.validation.monte_carlo import monte_carlo
from ohmystock.core.validation.stress import stress_test
from ohmystock.core.validation._market import equal_weight_benchmark
from ohmystock.core.validation.regime import regime_test
from ohmystock.core.validation.correlation import correlation
from ohmystock.core.validation.factor_exposure import factor_exposure
from ohmystock.core.validation.economic_edge import economic_edge
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.core.strategy.momentum import Momentum


# 전략 레지스트리: params dict → 전략 인스턴스
STRATEGIES = {
    "MACrossover": lambda p: MACrossover(
        short=p.get("short", 20), long=p.get("long", 60)),
    "Momentum": lambda p: Momentum(
        lookback=p.get("lookback", 90), top_k=p.get("top_k", 3)),
}


def build_strategy(name: str, params: dict):
    """이름과 파라미터로 전략 인스턴스를 생성. 미등록 이름은 ValueError."""
    if name not in STRATEGIES:
        raise ValueError(f"알 수 없는 전략: {name}")
    return STRATEGIES[name](params or {})


def _metric(key: str, label: str, value: float, display: str) -> dict:
    return {"key": key, "label": label, "value": float(value), "display": display}


def _validation(group: str, rep) -> dict:
    threshold = None if rep.threshold is None else float(rep.threshold)
    return {
        "group": group,
        "name": rep.name,
        "value": float(rep.value),
        "passed": bool(rep.passed),
        "threshold": threshold,
        "message": rep.message,
    }


def full_report(symbols, start, end, adapter, strategy, config) -> dict:
    """전체 백테스트 + 6개 성과지표 + 12개 검증을 JSON 직렬화 가능 dict로 반환."""
    bars = adapter.get_daily_bars(symbols, start, end)
    dv = validate_bars(bars)
    result = backtest(strategy, bars, config)
    benchmark = equal_weight_benchmark(bars)

    equity_curve = [
        {"date": idx.strftime("%Y-%m-%d"), "value": float(val)}
        for idx, val in result.equity_curve.items()
    ]

    mdd = M.max_drawdown(result)
    sharpe = M.sharpe_ratio(result, config)
    sortino = M.sortino_ratio(result, config)
    calmar = M.calmar_ratio(result, config)
    pf = M.profit_factor(result)
    rf = M.recovery_factor(result)
    metrics = [
        _metric("mdd", "MDD", mdd, f"{mdd:.2%}"),
        _metric("sharpe", "Sharpe", sharpe, f"{sharpe:.2f}"),
        _metric("sortino", "Sortino", sortino, f"{sortino:.2f}"),
        _metric("calmar", "Calmar", calmar, f"{calmar:.2f}"),
        _metric("profit_factor", "Profit Factor", pf, f"{pf:.2f}"),
        _metric("recovery_factor", "Recovery Factor", rf, f"{rf:.2f}"),
    ]

    validations = [
        _validation("G2", kelly_criterion(result)),
        _validation("G2", ruin_probability(result)),
        _validation("G2", capacity_analysis(result, bars, config)),
        _validation("G3", out_of_sample(result, config)),
        _validation("G3", walk_forward(result, config)),
        _validation("G3", monte_carlo(result)),
        _validation("G3", stress_test(result)),
        _validation("G4", regime_test(result, benchmark)),
        _validation("G4", correlation(result, benchmark)),
        _validation("G4", factor_exposure(result, {"market": benchmark})),
        _validation("G4", economic_edge(result, benchmark, config)),
    ]

    return {
        "strategy": type(strategy).__name__,
        "symbols": list(symbols),
        "start": str(start),
        "end": str(end),
        "final_equity": float(result.equity_curve.iloc[-1]),
        "data_validation": {
            "passed": bool(dv.passed),
            "issues": list(dv.issues),
            "warnings": list(dv.warnings),
        },
        "equity_curve": equity_curve,
        "metrics": metrics,
        "validations": validations,
    }
