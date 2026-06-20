"""KIS 모의투자 스모크 (사용자 실행 전용).

기본은 모의투자(paper). --live 를 줘야 실전 도메인을 쓴다.
실주문은 --order SYMBOL NOTIONAL 와 --i-understand-real-money 가 함께 있어야 실행한다.

준비:
  export KIS_APP_KEY=...  KIS_APP_SECRET=...  KIS_ACCOUNT_NO=12345678-01

사용:
  uv run python scripts/kis_smoke.py                 # 토큰+잔고+보유만(안전)
  uv run python scripts/kis_smoke.py --order 005930 50000 --i-understand-real-money
"""

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ohmystock.core.broker.base import Order
from ohmystock.core.broker.kis import KISBroker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kis_smoke")
    p.add_argument("--live", action="store_true", help="실전 도메인 사용(기본: 모의투자)")
    p.add_argument("--order", nargs=2, metavar=("SYMBOL", "NOTIONAL"), default=None,
                   help="소량 주문. 예: --order 005930 50000")
    p.add_argument("--i-understand-real-money", action="store_true",
                   help="실주문 실행에 필수")
    return p


def main(argv=None, broker=None) -> int:
    args = build_parser().parse_args(argv)

    if args.order and not args.i_understand_real_money:
        print("거부: 실주문은 --i-understand-real-money 가 필요합니다.", file=sys.stderr)
        return 2

    if broker is None:
        broker = KISBroker(paper=not args.live)
    print(f"[1] 토큰 발급 … (paper={getattr(broker, 'paper', None)})")
    broker.issue_token()
    print("    OK")
    acct = broker.get_account()
    print(f"[2] account: equity={acct.equity} cash={acct.cash}")
    print(f"[3] positions: {broker.get_positions()}")

    if args.order:
        symbol, notional = args.order[0], float(args.order[1])
        print(f"[4] 주문 제출: BUY {symbol} ~{notional}")
        broker.submit_order(Order(symbol=symbol, side="buy", notional=notional))
        print("    제출됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
