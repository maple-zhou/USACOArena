"""Standalone Flask application for the USACOArena management UI."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from flask import Flask

from .blueprint import register_ui_blueprint


DEFAULT_BASE_DIR = Path(__file__).resolve().parents[2]


def create_app(base_dir: Optional[Path] = None) -> Flask:
    """Create a Flask app that only serves the management UI."""

    app = Flask(__name__, static_folder="static", template_folder="templates")
    register_ui_blueprint(app, base_dir=base_dir or DEFAULT_BASE_DIR)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the USACOArena competition management dashboard"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind the UI server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5500,
        help="Port to bind the UI server (default: 5500)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=DEFAULT_BASE_DIR,
        help="Repository root containing config/ and scripts/ (default: project root)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Flask debug mode",
    )

    args = parser.parse_args()

    app = create_app(args.base_dir)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
