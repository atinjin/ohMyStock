import argparse

from ohmystock.config import Config
from ohmystock.core.data.cache import ParquetCache
from ohmystock.core.data.yfinance_adapter import YFinanceAdapter
from ohmystock.paper.service import PaperService
from ohmystock.paper.sqlite_store import SqlitePaperStore

DEFAULT_DB = "state/paper.db"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ohmystock.paper")
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init")
    pi.add_argument("--strategy", required=True)
    pi.add_argument("--symbols", required=True, help="쉼표 구분")
    pi.add_argument("--capital", type=float, default=5_000_000)
    pi.add_argument("--start", required=True)
    pi.add_argument("--end", required=True)

    sub.add_parser("step")
    pr = sub.add_parser("run")
    pr.add_argument("--steps", type=int, default=None)
    pr.add_argument("--to", default=None)
    sub.add_parser("status")
    return p


def run_cli(argv=None, adapter=None) -> None:
    args = build_parser().parse_args(argv)
    if adapter is None:
        adapter = YFinanceAdapter(cache=ParquetCache(".cache"))
    svc = PaperService(SqlitePaperStore(args.db), adapter, Config())

    if args.cmd == "init":
        svc.init_account(args.strategy, {}, args.symbols.split(","),
                         args.capital, args.start, args.end)
        print("초기화 완료")
    elif args.cmd == "step":
        res = svc.step()
        print("완료(더 진행할 거래일 없음)" if res is None else res)
    elif args.cmd == "run":
        results = svc.run(steps=args.steps, to=args.to)
        print(f"{len(results)} 스텝 진행")
    elif args.cmd == "status":
        print(svc.get_state())


def main() -> None:
    run_cli()


if __name__ == "__main__":
    main()
