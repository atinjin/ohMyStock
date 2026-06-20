import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kis_smoke.py"


def _load():
    spec = importlib.util.spec_from_file_location("kis_smoke", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeBroker:
    def __init__(self):
        self.orders = []

    def issue_token(self):
        return "tok"

    def get_account(self):
        from ohmystock.core.broker.base import Account
        return Account(equity=1000000.0, cash=1000000.0)

    def get_positions(self):
        return {}

    def submit_order(self, order):
        self.orders.append(order)


def test_parser_defaults():
    args = _load().build_parser().parse_args([])
    assert args.order is None
    assert args.live is False


def test_main_no_order_zero_submits():
    fake = _FakeBroker()
    rc = _load().main([], broker=fake)
    assert rc == 0
    assert fake.orders == []


def test_main_order_without_flag_rejected():
    fake = _FakeBroker()
    rc = _load().main(["--order", "005930", "50000"], broker=fake)
    assert rc == 2
    assert fake.orders == []


def test_main_order_with_flag_submits():
    fake = _FakeBroker()
    rc = _load().main(["--order", "005930", "50000", "--i-understand-real-money"],
                      broker=fake)
    assert rc == 0
    assert len(fake.orders) == 1
    assert fake.orders[0].symbol == "005930"
