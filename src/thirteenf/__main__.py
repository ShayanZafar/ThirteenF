"""python -m thirteenf COMMAND [options] runs one of the app's commands by its short name.

scripts\\run.cmd and scripts/run.sh call this with the Python in .venv, so a command never
runs on another Python that happens to be first on PATH. With no command, or an unknown
one, it lists the commands.
"""

import runpy
import sys

COMMANDS = {
    "ingest": "download and load the SEC data, build the model, then tickers and prices",
    "refresh": "the scheduled update: ingest, then what entered and left Accumulate",
    "model": "rebuild the model tables from the loaded data",
    "prices": "daily prices and volume for the market, the watchlist and the candidates",
    "tickers": "map new CUSIPs to tickers (--retry-missing asks again about unknown ones)",
    "web": "serve the app at http://127.0.0.1:8000 (--open, --port, --reload)",
}


def usage() -> str:
    lines = ["Usage: scripts\\run.cmd COMMAND [options]   (scripts/run.sh on macOS and Linux)", ""]
    lines += [f"  {name:<8} {what}" for name, what in COMMANDS.items()]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in COMMANDS:
        if argv and argv[0] not in ("-h", "--help"):
            print(f"Unknown command: {argv[0]}\n", file=sys.stderr)
        print(usage(), file=sys.stderr)
        return 0 if argv[:1] in (["-h"], ["--help"]) else 2
    name, rest = argv[0], argv[1:]
    sys.argv = [f"python -m thirteenf.{name}", *rest]
    try:
        runpy.run_module(f"thirteenf.{name}", run_name="__main__", alter_sys=True)
    except SystemExit as stop:
        return stop.code if isinstance(stop.code, int) else (0 if stop.code is None else 1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
