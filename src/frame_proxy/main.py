from __future__ import annotations

import argparse
from pathlib import Path

from frame_proxy.app import build_router
from frame_proxy.config import Settings
from frame_proxy.http.server import build_server
from frame_proxy.media.avi_writer import build_sample_avi


def _serve(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    router = build_router(settings)
    server = build_server(args.host, args.port, router=router, settings=settings)
    host, port = server.server_address[:2]
    print(f"Frame Proxy Inspector listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _demo_avi(args: argparse.Namespace) -> int:
    output = Path(args.output).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = build_sample_avi(width=args.width, height=args.height, fps=args.fps)
    output.write_bytes(payload)
    print(f"wrote {len(payload)} bytes to {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="frame-proxy-inspector")
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="start the HTTP service")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(function=_serve)

    demo = commands.add_parser("demo-avi", help="write deterministic demonstration footage")
    demo.add_argument("--output", required=True)
    demo.add_argument("--width", type=int, default=128)
    demo.add_argument("--height", type=int, default=72)
    demo.add_argument("--fps", type=int, default=12)
    demo.set_defaults(function=_demo_avi)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())

