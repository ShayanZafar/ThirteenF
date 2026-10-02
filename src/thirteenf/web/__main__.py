"""python -m thirteenf.web serves the app at http://127.0.0.1:8000."""

import argparse
from pathlib import Path

import uvicorn

import thirteenf


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.web")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart when the app's Python code changes")
    args = parser.parse_args()
    uvicorn.run(
        "thirteenf.web.app:app",
        host="127.0.0.1",
        port=args.port,
        reload=args.reload,
        # Watch only the package: templates reload on their own, and .venv/,
        # tests/ and data/ would otherwise restart the server for nothing.
        reload_dirs=[str(Path(thirteenf.__file__).parent)] if args.reload else None,
    )


if __name__ == "__main__":
    main()
