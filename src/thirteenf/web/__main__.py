"""python -m thirteenf.web serves the app at http://127.0.0.1:8000."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m thirteenf.web")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart when code changes")
    args = parser.parse_args()
    uvicorn.run("thirteenf.web.app:app", host="127.0.0.1", port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
