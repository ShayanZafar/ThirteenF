"""python -m thirteenf.ingest downloads the Form 13F data sets and loads them."""

import argparse
import sys

from thirteenf.config import MissingUserAgent


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.ingest")
    parser.add_argument("--download-only", action="store_true", help="download zips, do not load")
    parser.add_argument("--no-download", action="store_true", help="load the zips already in data/raw/")
    args = parser.parse_args()

    from thirteenf.ingest import sec

    try:
        if not args.no_download:
            sec.download_all()
    except MissingUserAgent as err:
        print(err, file=sys.stderr)
        return 2
    if args.download_only:
        return 0

    from thirteenf.ingest import load
    from thirteenf.model import build

    load.load_all()
    build.build_all()
    return 0


if __name__ == "__main__":
    sys.exit(main())
