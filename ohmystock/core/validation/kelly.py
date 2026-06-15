from ohmystock.core.validation.base import ValidationReport
from ohmystock.core.backtest.result import BacktestResult


def kelly_criterion(result: BacktestResult, threshold: float = 0.0) -> ValidationReport:
    """켈리 기준 f* = p - (1 - p)/b. 하프켈리도 함께 보고한다. ⑨"""
    pnl = result.trades["pnl"] if "pnl" in result.trades else []
    wins = pnl[pnl > 0] if len(pnl) else []
    losses = pnl[pnl < 0] if len(pnl) else []

    if len(pnl) == 0 or len(wins) == 0 or len(losses) == 0:
        return ValidationReport(
            name="Kelly",
            value=0.0,
            passed=False,
            threshold=threshold,
            message="거래 부족 또는 손익 부족",
        )

    p = len(wins) / len(pnl)
    avg_win = wins.mean()
    avg_loss = abs(losses.mean())
    b = avg_win / avg_loss
    f_star = p - (1 - p) / b
    half_kelly = f_star / 2

    value = float(f_star)
    passed = bool(f_star > threshold)
    message = (
        f"켈리 f*={f_star:.2f}, 하프켈리={half_kelly:.2f} "
        f"(승률 {p:.2f}, 손익비 {b:.2f})"
    )
    return ValidationReport(
        name="Kelly",
        value=value,
        passed=passed,
        threshold=threshold,
        message=message,
    )
