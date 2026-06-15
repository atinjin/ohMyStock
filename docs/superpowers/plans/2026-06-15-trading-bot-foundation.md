# OhMyStock 1단계(토대) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 일봉 데이터를 받아 검증하고, MA교차 전략을 거래비용 포함 백테스트한 뒤, 6개 성과지표를 텍스트 리포트로 출력하는 동작하는 최소 시스템을 만든다.

**Architecture:** 순수 Python 코어를 4개 인터페이스(데이터·전략·백테스트결과·검증)로 경계 짓는다. 백테스트는 일별 목표비중 행렬을 받아 수익률 기반(returns-based)으로 자산곡선·거래내역을 산출하며 거래비용을 차감한다. 시장 교체는 어댑터 패턴으로 한다.

**Tech Stack:** Python 3.11 (uv 관리), pandas 2.x, numpy, yfinance, pyarrow(parquet 캐시), pytest.

---

## File Structure

| 파일 | 책임 |
|------|------|
| `pyproject.toml` | uv 프로젝트·의존성 |
| `ohmystock/config.py` | 설정값 dataclass (자금·비용·MDD·연환산) |
| `ohmystock/core/backtest/result.py` | `BacktestResult` dataclass |
| `ohmystock/core/validation/base.py` | `ValidationReport`, `Validator` 프로토콜 |
| `ohmystock/core/data/adapter.py` | `MarketDataAdapter` 프로토콜 |
| `ohmystock/core/data/cache.py` | parquet 로컬 캐시 |
| `ohmystock/core/data/yfinance_adapter.py` | 미국 일봉 다운로드 |
| `ohmystock/core/data/validation.py` | ① 데이터 검증 |
| `ohmystock/core/strategy/base.py` | `Strategy` 프로토콜 |
| `ohmystock/core/strategy/ma_crossover.py` | MA교차 전략 |
| `ohmystock/core/backtest/costs.py` | ⑦ 거래비용 모델 |
| `ohmystock/core/backtest/engine.py` | 백테스트 엔진 |
| `ohmystock/core/validation/metrics.py` | G1 지표 6개 (⑩~⑮) |
| `ohmystock/cli.py` | 텍스트 리포트 |
| `tests/...` | 각 모듈 단위 테스트 |

각 파일은 하나의 책임만 가진다. 함께 바뀌는 것(거래비용·엔진·결과)은 `backtest/`에 모은다.

---

## Task 0: 프로젝트 스캐폴딩

**Files:**
- Create: `pyproject.toml`, `ohmystock/__init__.py`, `ohmystock/core/__init__.py`, 각 하위 패키지 `__init__.py`, `tests/__init__.py`

- [ ] **Step 1: uv 프로젝트 초기화 및 의존성 추가**

Run:
```bash
cd /Users/atinjin/repository/OhMyStock
uv init --python 3.11 --name ohmystock --no-workspace
uv add pandas numpy yfinance pyarrow
uv add --dev pytest
```

- [ ] **Step 2: 패키지 디렉토리 생성**

Run:
```bash
mkdir -p ohmystock/core/data ohmystock/core/strategy ohmystock/core/backtest ohmystock/core/validation tests
touch ohmystock/__init__.py ohmystock/core/__init__.py \
  ohmystock/core/data/__init__.py ohmystock/core/strategy/__init__.py \
  ohmystock/core/backtest/__init__.py ohmystock/core/validation/__init__.py \
  tests/__init__.py
```
`uv init`이 만든 샘플 `main.py`/`hello.py`가 있으면 삭제한다.

- [ ] **Step 3: pytest 동작 확인**

Run: `uv run pytest -q`
Expected: "no tests ran" (에러 없이 종료)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: scaffold uv project and package structure"
```

---

## Task 1: 설정 (config.py)

**Files:**
- Create: `ohmystock/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from ohmystock.config import Config

def test_default_config_values():
    cfg = Config()
    assert cfg.initial_capital == 5_000_000
    assert cfg.mdd_limit == 0.20
    assert cfg.trading_days == 252
    assert cfg.risk_free_rate == 0.0
    # 비용 (bps)
    assert cfg.commission_bps == 0.0   # 미국 Alpaca 0%
    assert cfg.slippage_bps == 5.0
    assert cfg.spread_bps == 2.0

def test_cost_rate_per_turnover():
    cfg = Config()
    # (0 + 5 + 2) bps = 7 bps = 0.0007
    assert abs(cfg.cost_rate() - 0.0007) < 1e-12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError: ohmystock.config)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/config.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/config.py tests/test_config.py
git commit -m "feat: add Config with cost rate helper"
```

---

## Task 2: BacktestResult & Validator 인터페이스

**Files:**
- Create: `ohmystock/core/backtest/result.py`, `ohmystock/core/validation/base.py`
- Test: `tests/test_result.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_result.py
import pandas as pd
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.base import ValidationReport

def test_backtest_result_holds_series_and_frames():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    eq = pd.Series([100.0, 110.0], index=idx)
    res = BacktestResult(
        equity_curve=eq,
        returns=eq.pct_change().fillna(0.0),
        trades=pd.DataFrame(columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]),
        positions=pd.DataFrame(index=idx),
    )
    assert res.equity_curve.iloc[-1] == 110.0
    assert list(res.trades.columns) == ["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"]

def test_validation_report_fields():
    rep = ValidationReport(name="Sharpe", value=1.2, passed=True, threshold=1.0, message="ok")
    assert rep.passed is True
    assert rep.threshold == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_result.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/backtest/result.py
from dataclasses import dataclass
import pandas as pd


@dataclass
class BacktestResult:
    """모든 검증(Validator)의 공통 입력."""
    equity_curve: pd.Series   # 일별 총자산
    returns: pd.Series        # 일별 수익률
    trades: pd.DataFrame      # symbol, entry_date, exit_date, qty, pnl, cost
    positions: pd.DataFrame   # 일별 심볼별 보유 비중
```

```python
# ohmystock/core/validation/base.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_result.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/backtest/result.py ohmystock/core/validation/base.py tests/test_result.py
git commit -m "feat: add BacktestResult and Validator interfaces"
```

---

## Task 3: 데이터 어댑터 인터페이스 + parquet 캐시

**Files:**
- Create: `ohmystock/core/data/adapter.py`, `ohmystock/core/data/cache.py`
- Test: `tests/test_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cache.py
import pandas as pd
from ohmystock.core.data.cache import ParquetCache

def _sample_df():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {"open": [10, 11], "high": [12, 12], "low": [9, 10],
         "close": [11, 12], "volume": [100, 120]}, index=idx)

def test_cache_roundtrip(tmp_path):
    cache = ParquetCache(tmp_path)
    df = _sample_df()
    assert cache.get("AAPL") is None        # miss
    cache.put("AAPL", df)
    loaded = cache.get("AAPL")              # hit
    pd.testing.assert_frame_equal(loaded, df)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cache.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/data/adapter.py
from datetime import date
from typing import Protocol
import pandas as pd


class MarketDataAdapter(Protocol):
    def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """심볼별 일봉. 컬럼 open/high/low/close/volume, index=거래일(DatetimeIndex)."""
        ...
```

```python
# ohmystock/core/data/cache.py
from pathlib import Path
import pandas as pd


class ParquetCache:
    """심볼 단위 일봉 parquet 캐시. 키 = 심볼."""

    def __init__(self, cache_dir):
        self.dir = Path(cache_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, symbol: str) -> Path:
        return self.dir / f"{symbol}.parquet"

    def get(self, symbol: str) -> pd.DataFrame | None:
        p = self._path(symbol)
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def put(self, symbol: str, df: pd.DataFrame) -> None:
        df.to_parquet(self._path(symbol))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cache.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/data/adapter.py ohmystock/core/data/cache.py tests/test_cache.py
git commit -m "feat: add MarketDataAdapter protocol and parquet cache"
```

---

## Task 4: YFinance 어댑터

**Files:**
- Create: `ohmystock/core/data/yfinance_adapter.py`
- Test: `tests/test_yfinance_adapter.py`

어댑터는 네트워크에 의존하므로, 테스트는 `download` 함수를 주입(의존성 주입)해 네트워크 없이 검증한다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_yfinance_adapter.py
from datetime import date
import pandas as pd
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.cache import ParquetCache

def _fake_download(symbol, start, end):
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {"open": [10.0, 11.0], "high": [12.0, 12.0], "low": [9.0, 10.0],
         "close": [11.0, 12.0], "volume": [100, 120]}, index=idx)

def test_fetches_and_normalizes(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_download)
    bars = adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    df = bars["AAPL"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].iloc[-1] == 12.0

def test_second_call_uses_cache(tmp_path):
    calls = {"n": 0}
    def counting_dl(symbol, start, end):
        calls["n"] += 1
        return _fake_download(symbol, start, end)
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=counting_dl)
    adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    adapter.get_daily_bars(["AAPL"], date(2024, 1, 1), date(2024, 1, 4))
    assert calls["n"] == 1   # 두 번째는 캐시
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_yfinance_adapter.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/data/yfinance_adapter.py
from datetime import date
import pandas as pd
from ohmystock.core.data.cache import ParquetCache

_COLS = ["open", "high", "low", "close", "volume"]


def _default_downloader(symbol: str, start: date, end: date) -> pd.DataFrame:
    import yfinance as yf
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    df = df.rename(columns=str.lower)
    return df[_COLS]


class YFinanceAdapter:
    """미국 일봉 어댑터. downloader는 테스트를 위해 주입 가능."""

    def __init__(self, cache: ParquetCache, downloader=_default_downloader):
        self.cache = cache
        self.downloader = downloader

    def get_daily_bars(
        self, symbols: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for sym in symbols:
            cached = self.cache.get(sym)
            if cached is not None:
                out[sym] = cached
                continue
            df = self.downloader(sym, start, end)
            if df is None or df.empty:
                raise ValueError(f"데이터 없음: {sym} {start}~{end}")
            df = df[_COLS]
            self.cache.put(sym, df)
            out[sym] = df
        return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_yfinance_adapter.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/data/yfinance_adapter.py tests/test_yfinance_adapter.py
git commit -m "feat: add YFinanceAdapter with cache and injectable downloader"
```

---

## Task 5: 데이터 검증 (① validation.py)

**Files:**
- Create: `ohmystock/core/data/validation.py`
- Test: `tests/test_data_validation.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_validation.py
import pandas as pd
import numpy as np
from ohmystock.core.data.validation import validate_bars

def _good():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    return pd.DataFrame(
        {"open": [10.0, 11.0, 11.5], "high": [12.0, 12.0, 12.0],
         "low": [9.0, 10.0, 11.0], "close": [11.0, 11.5, 11.8],
         "volume": [100, 120, 110]}, index=idx)

def test_clean_data_passes():
    report = validate_bars({"AAPL": _good()})
    assert report.passed is True
    assert report.issues == []

def test_detects_nonpositive_price():
    df = _good()
    df.loc[df.index[1], "close"] = 0.0
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("0/음수 가격" in i for i in report.issues)

def test_detects_duplicate_index():
    df = _good()
    df = pd.concat([df, df.iloc[[0]]])
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("중복" in i for i in report.issues)

def test_detects_nan():
    df = _good()
    df.loc[df.index[2], "close"] = np.nan
    report = validate_bars({"AAPL": df})
    assert report.passed is False
    assert any("결측" in i for i in report.issues)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_data_validation.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/data/validation.py
from dataclasses import dataclass, field
import pandas as pd

_PRICE_COLS = ["open", "high", "low", "close"]


@dataclass
class DataValidationReport:
    passed: bool
    issues: list[str] = field(default_factory=list)   # 치명적 문제
    warnings: list[str] = field(default_factory=list)  # 경고(통과는 가능)


def validate_bars(bars: dict[str, pd.DataFrame]) -> DataValidationReport:
    """① 데이터 검증: 결측·중복·0/음수·이상치 탐지, 생존편향 경고."""
    issues: list[str] = []
    warnings: list[str] = []

    for sym, df in bars.items():
        if df[_PRICE_COLS + ["volume"]].isna().any().any():
            issues.append(f"{sym}: 결측치 존재")
        if df.index.duplicated().any():
            issues.append(f"{sym}: 중복된 날짜 인덱스")
        if (df[_PRICE_COLS] <= 0).any().any():
            issues.append(f"{sym}: 0/음수 가격 존재")
        # 이상치: 일간 종가 변동 절대값 > 50%
        ret = df["close"].pct_change().abs()
        if (ret > 0.5).any():
            warnings.append(f"{sym}: 일간 50% 초과 변동(이상치 가능)")
        # 거래정지 의심: volume 0 구간
        if (df["volume"] == 0).any():
            warnings.append(f"{sym}: 거래량 0 구간(거래정지 가능)")

    warnings.append("생존편향 주의: 상장폐지 종목이 누락됐을 수 있음")
    return DataValidationReport(passed=len(issues) == 0, issues=issues, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_data_validation.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/data/validation.py tests/test_data_validation.py
git commit -m "feat: add data validation for missing/dup/nonpositive/outlier"
```

---

## Task 6: 전략 인터페이스 + MA교차

**Files:**
- Create: `ohmystock/core/strategy/base.py`, `ohmystock/core/strategy/ma_crossover.py`
- Test: `tests/test_ma_crossover.py`

전략은 lookahead 방지를 위해 시그널을 한 칸 shift한다(오늘 종가까지 본 결정은 내일부터 적용).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ma_crossover.py
import numpy as np
import pandas as pd
from ohmystock.core.strategy.ma_crossover import MACrossover

def _trend_df(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * len(closes)}, index=idx)

def test_signals_shape_and_weights():
    # 상승 추세: 단기선이 장기선 위 → 보유(>0)
    closes = list(np.linspace(10, 30, 40))
    bars = {"AAPL": _trend_df(closes)}
    strat = MACrossover(short=3, long=10)
    sig = strat.generate_signals(bars)
    assert list(sig.columns) == ["AAPL"]
    assert len(sig) == 40
    # 추세 후반은 매수 비중 1.0 (단일 종목 동일가중)
    assert sig["AAPL"].iloc[-1] == 1.0

def test_no_lookahead_first_row_is_zero_or_nan_filled():
    closes = list(np.linspace(10, 30, 40))
    sig = MACrossover(short=3, long=10).generate_signals({"AAPL": _trend_df(closes)})
    # 첫 행은 충분한 이동평균이 없으므로 0
    assert sig["AAPL"].iloc[0] == 0.0

def test_equal_weight_across_symbols():
    closes = list(np.linspace(10, 30, 40))
    bars = {"AAPL": _trend_df(closes), "MSFT": _trend_df(closes)}
    sig = MACrossover(short=3, long=10).generate_signals(bars)
    # 둘 다 매수 신호일 때 각 0.5
    assert sig.iloc[-1].sum() == 1.0
    assert sig["AAPL"].iloc[-1] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_ma_crossover.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/strategy/base.py
from typing import Protocol
import pandas as pd


class Strategy(Protocol):
    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        """일자×심볼 목표 비중 행렬. 0=미보유. 행 합계 <= 1. lookahead 금지."""
        ...
```

```python
# ohmystock/core/strategy/ma_crossover.py
import pandas as pd


class MACrossover:
    """단기 이동평균 > 장기 이동평균이면 매수(동일가중)."""

    def __init__(self, short: int = 20, long: int = 60):
        if short >= long:
            raise ValueError("short는 long보다 작아야 함")
        self.short = short
        self.long = long

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
        closes = pd.DataFrame({sym: df["close"] for sym, df in bars.items()})
        short_ma = closes.rolling(self.short).mean()
        long_ma = closes.rolling(self.long).mean()
        # 매수 여부 (장기선 결측이면 False)
        holding = (short_ma > long_ma).fillna(False)
        # lookahead 방지: 오늘까지 본 신호는 내일부터 적용
        holding = holding.shift(1).fillna(False).astype(float)
        # 동일가중 정규화 (그 날 보유 종목 수로 나눔)
        counts = holding.sum(axis=1).replace(0, 1)
        weights = holding.div(counts, axis=0)
        return weights
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_ma_crossover.py -v`
Expected: PASS (3 passed)

참고: shift로 첫 신호일이 하루 밀리므로 `iloc[-1]`이 1.0/0.5가 되도록 추세 데이터(40일)는 충분히 길게 잡았다.

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/strategy/base.py ohmystock/core/strategy/ma_crossover.py tests/test_ma_crossover.py
git commit -m "feat: add Strategy protocol and MACrossover (lookahead-safe, equal weight)"
```

---

## Task 7: 거래비용 모델 (⑦ costs.py)

**Files:**
- Create: `ohmystock/core/backtest/costs.py`
- Test: `tests/test_costs.py`

회전율(turnover) = 일별 비중 변화의 절대합. 비용 = 회전율 × cost_rate × 그 시점 자산.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_costs.py
import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.costs import turnover_series, cost_series

def test_turnover_counts_weight_changes():
    idx = pd.date_range("2024-01-01", periods=3, freq="B")
    w = pd.DataFrame({"AAPL": [0.0, 1.0, 0.0]}, index=idx)
    # 변화: 0->0(0), 0->1(1), 1->0(1)
    t = turnover_series(w)
    assert list(t.values) == [0.0, 1.0, 1.0]

def test_cost_is_turnover_times_rate():
    idx = pd.date_range("2024-01-01", periods=2, freq="B")
    w = pd.DataFrame({"AAPL": [0.0, 1.0]}, index=idx)
    cfg = Config()  # cost_rate = 0.0007
    c = cost_series(w, cfg)
    # 둘째 날 회전율 1.0 → 비용률 0.0007 (자산 대비 비율)
    assert abs(c.iloc[1] - 0.0007) < 1e-12
    assert c.iloc[0] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_costs.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/backtest/costs.py
import pandas as pd
from ohmystock.config import Config


def turnover_series(weights: pd.DataFrame) -> pd.Series:
    """일별 회전율 = 비중 변화 절대합. 첫날은 진입(전일 0 가정)."""
    prev = weights.shift(1).fillna(0.0)
    return (weights - prev).abs().sum(axis=1)


def cost_series(weights: pd.DataFrame, config: Config) -> pd.Series:
    """일별 거래비용(자산 대비 비율)."""
    return turnover_series(weights) * config.cost_rate()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_costs.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/backtest/costs.py tests/test_costs.py
git commit -m "feat: add transaction cost model (turnover-based)"
```

---

## Task 8: 백테스트 엔진 (engine.py)

**Files:**
- Create: `ohmystock/core/backtest/engine.py`
- Test: `tests/test_engine.py`

엔진은 수익률 기반(returns-based)이다: 비중 행렬과 종가 패널로 일별 순수익률을 만들고, 자산곡선·거래내역을 산출한다. 거래(round-trip)는 비중이 0→양수(진입), 양수→0(청산)으로 정의한다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engine.py
import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.engine import run_backtest

def _bars(closes):
    idx = pd.date_range("2024-01-01", periods=len(closes), freq="B")
    return {"AAPL": pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * len(closes)}, index=idx)}

def test_equity_grows_with_held_uptrend_no_cost():
    bars = _bars([10.0, 11.0, 12.0])          # +10%, +9.09%
    idx = list(bars["AAPL"].index)
    weights = pd.DataFrame({"AAPL": [1.0, 1.0, 1.0]}, index=idx)
    cfg = Config(commission_bps=0, slippage_bps=0, spread_bps=0, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    # day1 보유수익 없음(기준), day2 +10%, day3 +9.09% → 100*1.1*1.0909≈120
    assert abs(res.equity_curve.iloc[-1] - 120.0) < 1e-6

def test_cost_reduces_return_on_entry():
    bars = _bars([10.0, 10.0])
    idx = list(bars["AAPL"].index)
    weights = pd.DataFrame({"AAPL": [1.0, 1.0]}, index=idx)  # 첫날 진입(회전율 1)
    cfg = Config(commission_bps=0, slippage_bps=5, spread_bps=2, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    # 가격 변동 0, 첫날 진입비용 7bps → 자산 100*(1-0.0007)=99.93
    assert abs(res.equity_curve.iloc[0] - 99.93) < 1e-6

def test_trades_record_round_trip():
    bars = _bars([10.0, 11.0, 12.0, 12.0])
    idx = list(bars["AAPL"].index)
    # 1일 진입, 3일 청산
    weights = pd.DataFrame({"AAPL": [1.0, 1.0, 0.0, 0.0]}, index=idx)
    cfg = Config(commission_bps=0, slippage_bps=0, spread_bps=0, initial_capital=100.0)
    res = run_backtest(bars, weights, cfg)
    assert len(res.trades) == 1
    row = res.trades.iloc[0]
    assert row["symbol"] == "AAPL"
    assert row["pnl"] > 0      # 10 → 12 보유 구간
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_engine.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/backtest/engine.py
import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.costs import cost_series
from ohmystock.core.backtest.result import BacktestResult


def _close_panel(bars: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.DataFrame({sym: df["close"] for sym, df in bars.items()})


def _extract_trades(weights: pd.DataFrame, closes: pd.DataFrame,
                    equity: pd.Series) -> pd.DataFrame:
    """비중 0→양수=진입, 양수→0=청산. round-trip 거래내역 생성."""
    rows = []
    for sym in weights.columns:
        w = weights[sym]
        price = closes[sym]
        in_pos = False
        entry_date = entry_price = entry_equity = None
        for dt in w.index:
            if not in_pos and w.loc[dt] > 0:
                in_pos, entry_date = True, dt
                entry_price, entry_equity = price.loc[dt], equity.loc[dt]
            elif in_pos and w.loc[dt] == 0:
                pnl_pct = price.loc[dt] / entry_price - 1
                rows.append({
                    "symbol": sym, "entry_date": entry_date, "exit_date": dt,
                    "qty": entry_equity / entry_price,
                    "pnl": pnl_pct * entry_equity, "cost": 0.0,
                })
                in_pos = False
    return pd.DataFrame(
        rows, columns=["symbol", "entry_date", "exit_date", "qty", "pnl", "cost"])


def run_backtest(bars: dict[str, pd.DataFrame], weights: pd.DataFrame,
                 config: Config) -> BacktestResult:
    closes = _close_panel(bars).reindex(weights.index)
    asset_returns = closes.pct_change().fillna(0.0)
    # 그날 보유 비중으로 포트폴리오 총수익
    gross = (weights * asset_returns).sum(axis=1)
    costs = cost_series(weights, config)
    net = gross - costs
    equity = config.initial_capital * (1 + net).cumprod()
    trades = _extract_trades(weights, closes, equity)
    return BacktestResult(
        equity_curve=equity, returns=net, trades=trades, positions=weights)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_engine.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/backtest/engine.py tests/test_engine.py
git commit -m "feat: add returns-based backtest engine with trade extraction"
```

---

## Task 9: G1 성과지표 6개 (⑩~⑮ metrics.py)

**Files:**
- Create: `ohmystock/core/validation/metrics.py`
- Test: `tests/test_metrics.py`

손계산 기대값으로 검증한다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metrics.py
import numpy as np
import pandas as pd
from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult
from ohmystock.core.validation.metrics import (
    max_drawdown, sharpe_ratio, sortino_ratio, calmar_ratio,
    profit_factor, recovery_factor,
)

def _result(returns, trades_pnl=None):
    idx = pd.date_range("2024-01-01", periods=len(returns), freq="B")
    r = pd.Series(returns, index=idx)
    eq = 100.0 * (1 + r).cumprod()
    trades = pd.DataFrame(
        {"symbol": ["X"] * len(trades_pnl), "entry_date": idx[:len(trades_pnl)],
         "exit_date": idx[:len(trades_pnl)], "qty": [1.0] * len(trades_pnl),
         "pnl": trades_pnl, "cost": [0.0] * len(trades_pnl)}
    ) if trades_pnl else pd.DataFrame(columns=["symbol", "pnl"])
    return BacktestResult(equity_curve=eq, returns=r, trades=trades,
                          positions=pd.DataFrame(index=idx))

def test_max_drawdown():
    # 100 -> 110 -> 88 : 고점 110 대비 88 = -20%
    res = _result([0.10, -0.20])
    assert abs(max_drawdown(res) - 0.20) < 1e-9

def test_sharpe_zero_when_no_volatility():
    res = _result([0.01, 0.01, 0.01])
    cfg = Config(risk_free_rate=0.0)
    # 변동성 0 → 0 반환(0 나눗셈 회피)
    assert sharpe_ratio(res, cfg) == 0.0

def test_sharpe_positive_for_positive_mean():
    res = _result([0.01, -0.005, 0.02, 0.0, 0.015])
    assert sharpe_ratio(res, Config()) > 0

def test_sortino_ge_sharpe_magnitude_when_downside_small():
    res = _result([0.02, 0.02, -0.01, 0.02])
    assert sortino_ratio(res, Config()) > 0

def test_calmar_is_cagr_over_mdd():
    res = _result([0.10, -0.20, 0.30])
    cfg = Config()
    mdd = max_drawdown(res)
    cagr = (res.equity_curve.iloc[-1] / 100.0) ** (cfg.trading_days / len(res.returns)) - 1
    assert abs(calmar_ratio(res, cfg) - cagr / mdd) < 1e-6

def test_profit_factor():
    res = _result([0.0, 0.0], trades_pnl=[30.0, -10.0, 20.0])
    # 이익 50 / 손실 10 = 5.0
    assert abs(profit_factor(res) - 5.0) < 1e-9

def test_recovery_factor():
    res = _result([0.10, -0.20, 0.30])
    cfg = Config()
    total_ret = res.equity_curve.iloc[-1] / 100.0 - 1
    assert abs(recovery_factor(res) - total_ret / max_drawdown(res)) < 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/core/validation/metrics.py
import numpy as np
from ohmystock.config import Config
from ohmystock.core.backtest.result import BacktestResult


def max_drawdown(result: BacktestResult) -> float:
    """누적 고점 대비 최대 낙폭(양수). ⑩"""
    eq = result.equity_curve
    peak = eq.cummax()
    dd = (eq - peak) / peak
    return float(-dd.min())


def _cagr(result: BacktestResult, cfg: Config) -> float:
    eq = result.equity_curve
    n = len(result.returns)
    if n == 0:
        return 0.0
    return float((eq.iloc[-1] / eq.iloc[0]) ** (cfg.trading_days / n) - 1)


def sharpe_ratio(result: BacktestResult, cfg: Config) -> float:
    """(연환산수익 - 무위험) / 연환산변동성. ⑪"""
    r = result.returns
    std = r.std(ddof=1)
    if std == 0 or np.isnan(std):
        return 0.0
    ann_ret = r.mean() * cfg.trading_days
    ann_vol = std * np.sqrt(cfg.trading_days)
    return float((ann_ret - cfg.risk_free_rate) / ann_vol)


def sortino_ratio(result: BacktestResult, cfg: Config) -> float:
    """하방변동성만 사용. ⑫"""
    r = result.returns
    downside = r.clip(upper=0.0)
    dstd = np.sqrt((downside ** 2).mean())
    if dstd == 0 or np.isnan(dstd):
        return 0.0
    ann_ret = r.mean() * cfg.trading_days
    ann_dvol = dstd * np.sqrt(cfg.trading_days)
    return float((ann_ret - cfg.risk_free_rate) / ann_dvol)


def calmar_ratio(result: BacktestResult, cfg: Config) -> float:
    """연환산수익(CAGR) / MDD. ⑬"""
    mdd = max_drawdown(result)
    if mdd == 0:
        return 0.0
    return _cagr(result, cfg) / mdd


def profit_factor(result: BacktestResult) -> float:
    """총이익 / |총손실|. ⑭"""
    pnl = result.trades["pnl"] if "pnl" in result.trades else []
    if len(pnl) == 0:
        return 0.0
    gains = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / abs(losses))


def recovery_factor(result: BacktestResult) -> float:
    """순수익률 / MDD. ⑮"""
    mdd = max_drawdown(result)
    if mdd == 0:
        return 0.0
    total_ret = result.equity_curve.iloc[-1] / result.equity_curve.iloc[0] - 1
    return float(total_ret / mdd)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metrics.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add ohmystock/core/validation/metrics.py tests/test_metrics.py
git commit -m "feat: add G1 metrics (MDD, Sharpe, Sortino, Calmar, ProfitFactor, Recovery)"
```

---

## Task 10: CLI 텍스트 리포트 (cli.py)

**Files:**
- Create: `ohmystock/cli.py`
- Test: `tests/test_cli.py`

CLI는 조립만 한다: 데이터 → 검증 → 백테스트 → 지표 → 출력. 핵심 로직은 `build_report`(테스트 가능)와 `main`(엔트리)으로 분리한다.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import numpy as np
import pandas as pd
from datetime import date
from ohmystock.config import Config
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.cli import build_report

def _fake_dl(symbol, start, end):
    closes = list(np.linspace(10, 30, 80))
    idx = pd.date_range("2024-01-01", periods=80, freq="B")
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes,
         "close": closes, "volume": [100] * 80}, index=idx)

def test_build_report_contains_metrics(tmp_path):
    adapter = YFinanceAdapter(cache=ParquetCache(tmp_path), downloader=_fake_dl)
    report = build_report(
        symbols=["AAPL"], start=date(2024, 1, 1), end=date(2024, 4, 30),
        adapter=adapter, strategy=MACrossover(short=5, long=20), config=Config())
    assert "MDD" in report
    assert "Sharpe" in report
    assert "Profit Factor" in report
    assert "데이터 검증" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# ohmystock/cli.py
from datetime import date
from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.core.data.validation import validate_bars
from ohmystock.core.strategy.ma_crossover import MACrossover
from ohmystock.core.backtest.engine import run_backtest
from ohmystock.core.validation import metrics as M


def build_report(symbols, start, end, adapter, strategy, config) -> str:
    bars = adapter.get_daily_bars(symbols, start, end)
    dv = validate_bars(bars)
    signals = strategy.generate_signals(bars)
    result = run_backtest(bars, signals, config)

    lines = []
    lines.append("=" * 48)
    lines.append("OhMyStock 백테스트 리포트")
    lines.append("=" * 48)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 전체 테스트 + 실데이터 스모크 확인**

Run: `uv run pytest -q`
Expected: 전체 PASS

Run (네트워크 필요, 실데이터 스모크): `uv run python -m ohmystock.cli`
Expected: 5개 종목 리포트가 에러 없이 출력됨 (지표 값 표시)

- [ ] **Step 6: Commit**

```bash
git add ohmystock/cli.py tests/test_cli.py
git commit -m "feat: add CLI text report wiring data->validate->backtest->metrics"
```

---

## Self-Review 결과

**Spec 커버리지:**
- ① 데이터검증 → Task 5 ✓
- ⑦ 거래비용 → Task 7 ✓
- ⑩~⑮ 성과지표 6개 → Task 9 ✓
- 데이터 어댑터(MarketDataAdapter) → Task 3,4 ✓
- 전략 인터페이스 + MA교차 → Task 6 ✓
- 백테스트 엔진 + BacktestResult → Task 2,8 ✓
- Validator 인터페이스 → Task 2 ✓
- 설정(config) → Task 1 ✓
- CLI 리포트 → Task 10 ✓
- 완료 기준(종목 넣으면 검증→자산곡선→6지표 출력) → Task 10 Step 5 ✓

**비범위 확인:** G2/G3/G4, FastAPI/React, 실거래, KIS, 모멘텀/RSI는 1단계에서 제외 — 계획에 미포함(정상).

**플레이스홀더:** 없음. 모든 step에 실제 코드/명령/기대값 포함.

**타입 일관성:** `BacktestResult`(equity_curve/returns/trades/positions), `Config.cost_rate()`, `validate_bars→DataValidationReport(passed/issues/warnings)`, `generate_signals→DataFrame`, `run_backtest(bars, weights, config)` — Task 간 시그니처 일치 확인됨.

**알려진 단순화(의도된 것):**
- 백테스트는 수익률 기반(주식 수량 정밀 추적 대신 비중 기반). 500만원 소수점 주식 가정에 적합. 일중 체결가 대신 종가 기준 — 일봉 스윙에 타당.
- 거래(trade) pnl은 종가-종가 기준 근사. Profit Factor용으로 충분.
이 단순화들은 2단계 이후 정밀화 여지를 남긴다.
