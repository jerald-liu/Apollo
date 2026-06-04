"""One-command launcher for the Apollo local app (APP-01, D-01, D-04).

Usage:
    python -m apollo.app [--port 5001] [--pairs-root data/pairs]

Mirrors apollo/scripts/eval_grade.py:
  - Binds 127.0.0.1 only (T-05-02, RESEARCH §Anti-Patterns)
  - debug=False always
  - threaded=True: polling /status during training must be served concurrently
    with the training daemon thread (RESEARCH Pitfall 1)

Adds vs eval_grade.py:
  - webbrowser.open after a short delay so Flask is listening first
  - threading.Timer(0.5, ...) avoids a race on slow machines
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser
from typing import Sequence

from apollo.app.app import create_app


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="apollo.app",
        description="Launch the Apollo local app on 127.0.0.1.",
    )
    parser.add_argument("--port", type=int, default=5001,
                        help="TCP port (default: 5001).")
    parser.add_argument("--pairs-root", default="data/pairs",
                        help="Path to pairs directory (default: data/pairs).")
    args = parser.parse_args(argv)

    app = create_app(pairs_root=args.pairs_root)
    url = f"http://127.0.0.1:{args.port}/"

    # Open browser after a short delay so Flask is already listening.
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    print(f"Apollo app: {url}", file=sys.stderr)

    # threaded=True: the /status polling endpoint must be served concurrently
    # with the training daemon thread (RESEARCH Pitfall 1, D-03).
    # host=127.0.0.1: local-only binding (T-05-02).
    app.run(host="127.0.0.1", port=args.port, debug=False, threaded=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
