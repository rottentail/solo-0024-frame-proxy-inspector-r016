from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from frame_proxy.config import Settings
from frame_proxy.http.router import RequestRouter
from frame_proxy.http.types import ResponseData


class FrameProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _handler_class(
    router: RequestRouter,
    settings: Settings,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._handle("GET")

        def do_PUT(self) -> None:
            self._handle("PUT")

        def do_POST(self) -> None:
            self._handle("POST")

        def _read_body(self) -> bytes:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise ValueError("Content-Length must be an integer") from exc
            if length < 0:
                raise ValueError("Content-Length must not be negative")
            if length > settings.max_upload_bytes:
                raise ValueError("request body exceeds the configured limit")
            payload = self.rfile.read(length)
            if len(payload) != length:
                raise ValueError("request body ended before Content-Length")
            return payload

        def _handle(self, method: str) -> None:
            try:
                body = self._read_body()
                response = router.handle(
                    method,
                    self.path,
                    {key.lower(): value for key, value in self.headers.items()},
                    body,
                )
            except ValueError as exc:
                response = ResponseData.json(
                    400,
                    {
                        "error": {
                            "code": "invalid_request",
                            "message": str(exc),
                        }
                    },
                )
            self._send(response)

        def _send(self, response: ResponseData) -> None:
            self.send_response(response.status)
            self.send_header("Content-Type", response.content_type)
            self.send_header("Content-Length", str(len(response.body)))
            self.send_header("Connection", "close")
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            if response.body:
                self.wfile.write(response.body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def build_server(
    host: str,
    port: int,
    *,
    router: RequestRouter,
    settings: Settings,
) -> FrameProxyServer:
    return FrameProxyServer((host, port), _handler_class(router, settings))
