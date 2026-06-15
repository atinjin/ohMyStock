from dataclasses import dataclass


@dataclass
class Config:
    """시스템 전역 설정. 모든 값은 설정으로 조정 가능."""
    initial_capital: float = 5_000_000      # 원
    mdd_limit: float = 0.20                  # 고점 대비 -20% 경고선
    trading_days: int = 252                  # 연환산 거래일수
    risk_free_rate: float = 0.0              # 무위험 연수익률
    commission_bps: float = 0.0              # 수수료 (미국 0)
    slippage_bps: float = 5.0                # 슬리피지
    spread_bps: float = 2.0                  # 스프레드(간이)

    def cost_rate(self) -> float:
        """회전율 1단위당 비용률 (bps 합 → 소수)."""
        return (self.commission_bps + self.slippage_bps + self.spread_bps) / 10_000
