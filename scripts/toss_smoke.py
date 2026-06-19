"""TOSS Invest 실계좌 스모크 (사용자 실행 전용).

경고: 토스증권 Open API는 모의투자(샌드박스)가 없어 모든 주문이 실제 체결된다.
주문은 --order SYMBOL NOTIONAL 와 --i-understand-real-money 를 함께 줄 때만 실행한다.

준비:
  export TOSS_CLIENT_ID=...   TOSS_CLIENT_SECRET=...
  (선택) export TOSS_ACCOUNT_SEQ=...

사용:
  uv run python scripts/toss_smoke.py                 # 토큰+계좌+보유만 확인(안전)
  uv run python scripts/toss_smoke.py --order AAPL 50 --i-understand-real-money
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (editable 설치 없이도 동작)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from ohmystock.core.broker.base import Order
from ohmystock.core.broker.toss import TossBroker


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="toss_smoke")
    p.add_argument("--currency", default="usd")
    p.add_argument("--order", nargs=2, metavar=("SYMBOL", "NOTIONAL"), default=None,
                   help="소량 실주문 (실거래!). 예: --order AAPL 50")
    p.add_argument("--i-understand-real-money", action="store_true",
                   help="실제 돈이 나가는 것을 이해함 — 주문 실행에 필수")
    return p


def main(argv=None, broker=None) -> int:
    args = build_parser().parse_args(argv)

    # 실주문 이중 게이트: --order 는 --i-understand-real-money 없이는 즉시 거부(네트워크 전).
    if args.order and not args.i_understand_real_money:
        print("거부: 실주문은 --i-understand-real-money 가 필요합니다 (실거래).",
              file=sys.stderr)
        return 2

    if broker is None:
        broker = TossBroker(currency=args.currency)
    print("[1] 토큰 발급 …")
    broker.issue_token()
    print("    OK")
    print(f"[2] accountSeq = {broker._resolve_account_seq()}")
    acct = broker.get_account()
    print(f"[3] account: equity={acct.equity} cash={acct.cash}")
    print(f"[4] positions: {broker.get_positions()}")

    if args.order:
        symbol, notional = args.order[0], float(args.order[1])
        print(f"[5] 실주문 제출: BUY {symbol} ~{notional} (실거래!)")
        broker.submit_order(Order(symbol=symbol, side="buy", notional=notional))
        print("    제출됨")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
