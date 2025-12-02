"""Entry point for running the monitoring service."""

from __future__ import annotations

import argparse

from app import bootstrap


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Network performance monitor")
    parser.add_argument("--config", help="Path to config.yaml", default="config.yaml")
    parser.add_argument("--host", default=None, help="Override web server host")
    parser.add_argument("--port", type=int, default=None, help="Override web server port")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    context = bootstrap(args.config)
    context.start()

    host = args.host or context.config.web.host
    port = args.port or context.config.web.port
    context.web_app.run(host=host, port=port, debug=args.debug)


if __name__ == "__main__":
    main()
