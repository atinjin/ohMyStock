from dataclasses import dataclass
import pandas as pd


@dataclass
class BacktestResult:
    """모든 검증(Validator)의 공통 입력."""
    equity_curve: pd.Series   # 일별 총자산
    returns: pd.Series        # 일별 수익률
    trades: pd.DataFrame      # symbol, entry_date, exit_date, qty, pnl, cost
    positions: pd.DataFrame   # 일별 심볼별 보유 비중
