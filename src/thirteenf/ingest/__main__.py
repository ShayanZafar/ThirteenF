"""python -m thirteenf.ingest downloads the Form 13F data sets and the companies'
cash flow data from the SEC, loads them, and then maps tickers and fetches daily
prices, each when its key is set."""

import argparse
import sys

from thirteenf.config import MissingUserAgent


def download() -> None:
    """Every SEC download of a run, through one client: one pacing for them all."""
    from thirteenf.ingest import sec, xbrl

    client = sec.SecClient()
    try:
        sec.download_all(client=client)
        xbrl.download_all(client=client)
    finally:
        client.close()


def load_and_build() -> None:
    from thirteenf.db import connect
    from thirteenf.ingest import load, xbrl
    from thirteenf.model import build

    load.load_all()
    with connect() as con:
        xbrl.load_all(con)
    build.build_all()

    from thirteenf.config import openfigi_api_key
    from thirteenf.tickers import update_tickers

    if openfigi_api_key():
        update_tickers()
    else:
        from thirteenf.config import ensure_settings_file

        print(
            f"Tickers: paste a free OpenFIGI key (openfigi.com) into {ensure_settings_file()}, "
            "then run python -m thirteenf.tickers"
        )
    from thirteenf.prices import update_prices

    update_prices()


def run(args: argparse.Namespace) -> int:
    try:
        if not args.no_download:
            download()
    except MissingUserAgent as err:
        print(err, file=sys.stderr)
        return 2
    except RuntimeError as err:  # the SEC kept refusing, or no links on its page: the message says what to do
        print(err, file=sys.stderr)
        return 1
    if not args.download_only:
        load_and_build()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.ingest")
    parser.add_argument("--download-only", action="store_true", help="download zips, do not load")
    parser.add_argument("--no-download", action="store_true", help="load the zips already in data/raw/")
    code = run(parser.parse_args())

    from thirteenf import health

    warning = health.warning()
    if warning:
        print(f"Sources: {warning} Details in {health.HEALTH_PATH}.")
    return code


if __name__ == "__main__":
    sys.exit(main())
