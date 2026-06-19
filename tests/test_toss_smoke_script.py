import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "toss_smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("toss_smoke", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parser_defaults_no_order():
    mod = _load()
    args = mod.build_parser().parse_args([])
    assert args.order is None
    assert args.i_understand_real_money is False


def test_parser_accepts_order():
    mod = _load()
    args = mod.build_parser().parse_args(
        ["--order", "AAPL", "500", "--i-understand-real-money"])
    assert args.order == ["AAPL", "500"]
    assert args.i_understand_real_money is True


class _FakeBroker:
    """주입형 가짜 브로커 — 실주문 호출을 기록만 한다(네트워크 0)."""

    def __init__(self):
        self.orders = []

    def issue_token(self):
        return "tok"

    def _resolve_account_seq(self):
        return 1

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=100.0, cash=100.0)

    def get_positions(self):
        return {}

    def submit_order(self, order):
        self.orders.append(order)


def test_main_no_order_places_zero_orders():
    mod = _load()
    fake = _FakeBroker()
    rc = mod.main([], broker=fake)
    assert rc == 0
    assert fake.orders == []          # 인자 없으면 읽기만, 주문 0


def test_main_order_without_flag_rejected_zero_orders():
    mod = _load()
    fake = _FakeBroker()
    rc = mod.main(["--order", "AAPL", "500"], broker=fake)
    assert rc == 2                    # 거부
    assert fake.orders == []          # 실주문 0


def test_main_order_with_flag_submits_one():
    mod = _load()
    fake = _FakeBroker()
    rc = mod.main(["--order", "AAPL", "500", "--i-understand-real-money"],
                  broker=fake)
    assert rc == 0
    assert len(fake.orders) == 1
    assert fake.orders[0].symbol == "AAPL"
    assert fake.orders[0].side == "buy"
