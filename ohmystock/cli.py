from datetime import date
from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.validation import validate_bars
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.core.backtest.engine import run_backtest
from ohmystock.core.validation import metrics as M
from ohmystock.core.validation.kelly import kelly_criterion
from ohmystock.core.validation.ruin import ruin_probability
from ohmystock.core.validation.capacity import capacity_analysis
from ohmystock.core.validation.out_of_sample import out_of_sample
from ohmystock.core.validation.walk_forward import walk_forward
from ohmystock.core.validation.monte_carlo import monte_carlo
from ohmystock.core.validation.stress import stress_test


def _vline(rep) -> str:
    """ValidationReport 한 줄 포맷."""
    mark = "✓" if rep.passed else "✗"
    return f"  {mark} {rep.name}: {rep.message}"


def build_report(symbols, start, end, adapter, strategy, config) -> str:
    bars = adapter.get_daily_bars(symbols, start, end)
    dv = validate_bars(bars)
    signals = strategy.generate_signals(bars)
    result = run_backtest(bars, signals, config)

    lines = []
    lines.append("=" * 48)
    lines.append("OhMyStock 백테스트 리포트")
    lines.append("=" * 48)
    lines.append(f"전략: {type(strategy).__name__}")
    lines.append(f"종목: {', '.join(symbols)}  기간: {start} ~ {end}")
    lines.append(f"데이터 검증: {'통과' if dv.passed else '실패'}")
    for w in dv.warnings:
        lines.append(f"  ⚠ {w}")
    for i in dv.issues:
        lines.append(f"  ✕ {i}")
    lines.append("-" * 48)
    lines.append(f"최종 자산: {result.equity_curve.iloc[-1]:,.0f}")
    lines.append("성과지표")
    lines.append(f"  ⑩ MDD            : {M.max_drawdown(result):.2%}")
    lines.append(f"  ⑪ Sharpe         : {M.sharpe_ratio(result, config):.2f}")
    lines.append(f"  ⑫ Sortino        : {M.sortino_ratio(result, config):.2f}")
    lines.append(f"  ⑬ Calmar         : {M.calmar_ratio(result, config):.2f}")
    lines.append(f"  ⑭ Profit Factor  : {M.profit_factor(result):.2f}")
    lines.append(f"  ⑮ Recovery Factor: {M.recovery_factor(result):.2f}")
    lines.append("-" * 48)
    lines.append("자금·리스크 (G2)")
    lines.append(_vline(kelly_criterion(result)))         # ⑨
    lines.append(_vline(ruin_probability(result)))        # ⑯
    lines.append(_vline(capacity_analysis(result, bars, config)))  # ⑧
    lines.append("-" * 48)
    lines.append("견고성 (G3)")
    lines.append(_vline(out_of_sample(result, config)))   # ④
    lines.append(_vline(walk_forward(result, config)))    # ③
    lines.append(_vline(monte_carlo(result)))             # ⑤
    lines.append(_vline(stress_test(result)))             # ⑥
    lines.append("=" * 48)
    return "\n".join(lines)


def main():
    config = Config()
    adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    symbols = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
    report = build_report(
        symbols=symbols, start=date(2020, 1, 1), end=date(2024, 1, 1),
        adapter=adapter, strategy=MACrossover(), config=config)
    print(report)


if __name__ == "__main__":
    main()
