from dataclasses import dataclass
from typing import Protocol


@dataclass
class Account:
    """계좌 스냅샷."""
    equity: float   # 총 자산(현금 + 포지션 평가액)
    cash: float


@dataclass
class Order:
    """체결 주문. notional은 거래할 양수 금액(소수 주식 허용)."""
    symbol: str
    side: str       # "buy" 또는 "sell"
    notional: float


class Broker(Protocol):
    def get_account(self) -> Account: ...
    def get_positions(self) -> dict[str, float]: ...  # 종목 -> 평가 금액
    def submit_order(self, order: Order) -> None: ...
