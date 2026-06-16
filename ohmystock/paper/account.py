from dataclasses import dataclass


@dataclass
class PaperAccount:
    """페이퍼 계좌 설정 + 현재 상태."""
    strategy: str
    params: dict
    symbols: list[str]
    initial_capital: float
    start_date: str
    end_date: str
    cursor_date: str | None
    cash: float
    peak_equity: float
