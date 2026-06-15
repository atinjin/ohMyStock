from dataclasses import dataclass
from typing import Protocol
from ohmystock.core.backtest.result import BacktestResult


@dataclass
class ValidationReport:
    name: str
    value: float
    passed: bool
    threshold: float | None
    message: str


class Validator(Protocol):
    name: str
    def evaluate(self, result: BacktestResult) -> ValidationReport: ...
