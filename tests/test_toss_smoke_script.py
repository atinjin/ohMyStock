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
