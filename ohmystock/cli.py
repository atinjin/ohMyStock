from datetime import date
from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.report import full_report


def _vline(v: dict) -> str:
    """검증 dict 한 줄 포맷."""
    mark = "✓" if v["passed"] else "✗"
    return f"  {mark} {v['name']}: {v['message']}"


# 성과지표 라벨 정렬 폭(좌측 정렬). 기존 출력 포맷을 그대로 유지한다.
_METRIC_LABELS = {
    "mdd": "⑩ MDD            ",
    "sharpe": "⑪ Sharpe         ",
    "sortino": "⑫ Sortino        ",
    "calmar": "⑬ Calmar         ",
    "profit_factor": "⑭ Profit Factor  ",
    "recovery_factor": "⑮ Recovery Factor",
}


def build_report(symbols, start, end, adapter, strategy, config) -> str:
    rep = full_report(symbols, start, end, adapter, strategy, config)
    dv = rep["data_validation"]
    metrics = {m["key"]: m for m in rep["metrics"]}
    vals = rep["validations"]
    by_group = {"G2": [], "G3": [], "G4": []}
    for v in vals:
        by_group[v["group"]].append(v)

    lines = []
    lines.append("=" * 48)
    lines.append("OhMyStock 백테스트 리포트")
    lines.append("=" * 48)
    lines.append(f"전략: {rep['strategy']}")
    lines.append(f"종목: {', '.join(symbols)}  기간: {start} ~ {end}")
    lines.append(f"데이터 검증: {'통과' if dv['passed'] else '실패'}")
    for w in dv["warnings"]:
        lines.append(f"  ⚠ {w}")
    for i in dv["issues"]:
        lines.append(f"  ✕ {i}")
    lines.append("-" * 48)
    lines.append(f"최종 자산: {rep['final_equity']:,.0f}")
    lines.append("성과지표")
    for key, label in _METRIC_LABELS.items():
        lines.append(f"  {label}: {metrics[key]['display']}")
    lines.append("-" * 48)
    lines.append("자금·리스크 (G2)")
    for v in by_group["G2"]:
        lines.append(_vline(v))
    lines.append("-" * 48)
    lines.append("견고성 (G3)")
    for v in by_group["G3"]:
        lines.append(_vline(v))
    lines.append("-" * 48)
    lines.append("시장구조 (G4)")
    for v in by_group["G4"]:
        lines.append(_vline(v))
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
