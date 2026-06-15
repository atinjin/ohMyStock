from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport


def capacity_analysis(
    result: BacktestResult,
    bars: dict,
    config: Config,
    max_participation: float = 0.1,
) -> ValidationReport:
    """전략의 최대 수용 가능 시드(capacity)를 추정한다.

    각 보유 심볼의 평균 일거래대금(ADV)에 시장참여율 상한(max_participation)을
    곱해 1회 주문 가능 금액을 구하고, 해당 심볼의 최대 보유비중으로 나눠
    심볼별 투입가능 시드를 역산한다. 가장 빡빡한(최소) 값이 전체 capacity다.
    """
    implied_capitals: list[float] = []
    for sym in result.positions.columns:
        if sym not in bars:
            continue
        bar = bars[sym]
        adv_dollar = float((bar["volume"] * bar["close"]).mean())
        max_order_dollar = max_participation * adv_dollar

        w_max = float(result.positions[sym].max())
        if w_max <= 0:
            # 한 번도 보유하지 않은 심볼은 제외.
            continue
        implied_capitals.append(max_order_dollar / w_max)

    if not implied_capitals:
        capacity = float("inf")
        return ValidationReport(
            name="Capacity",
            value=capacity,
            passed=True,
            threshold=float(config.initial_capital),
            message="보유 포지션 없음",
        )

    capacity = min(implied_capitals)
    value = float(capacity)
    passed = config.initial_capital <= capacity
    status = "여유" if passed else "초과 위험"
    message = (
        f"최대 투입가능 시드 ≈ {value:,.0f} "
        f"(현재 {config.initial_capital:,.0f}: {status})"
    )
    return ValidationReport(
        name="Capacity",
        value=value,
        passed=passed,
        threshold=float(config.initial_capital),
        message=message,
    )
