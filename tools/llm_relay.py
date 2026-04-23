#!/usr/bin/env python3
"""
Local relay server for Docker containers.

Why this exists:
- Some container environments can not TLS-connect to specific upstream hosts.
- Host machine can connect successfully.
- API/worker containers call this relay over plain HTTP at host.docker.internal.

This relay is not a generic open proxy. It forwards only to the configured upstream.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

HOST = os.getenv("LLM_RELAY_HOST", "127.0.0.1")
PORT = int(os.getenv("LLM_RELAY_PORT", "8787"))
UPSTREAM_BASE = os.getenv("LLM_RELAY_UPSTREAM", "https://open.xiaojingai.com").rstrip("/")
TIMEOUT = float(os.getenv("LLM_RELAY_TIMEOUT_SECONDS", "120"))

HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

RESPONSE_DROP_HEADERS = {
    # requests already returns decoded bytes in resp.content.
    # forwarding original encoding header can trigger downstream decode errors.
    "content-encoding",
    "content-length",
    "transfer-encoding",
    "connection",
}


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _read_body(self) -> bytes:
        raw_len = self.headers.get("Content-Length")
        if not raw_len:
            return b""
        try:
            length = int(raw_len)
        except ValueError:
            return b""
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _forward(self, method: str) -> None:
        target_url = f"{UPSTREAM_BASE}{self.path}"
        body = self._read_body()

        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in HOP_HEADERS
        }
        headers["Connection"] = "close"

        try:
            session = requests.Session()
            # Use host machine's direct network route by default.
            session.trust_env = False
            resp = session.request(
                method=method,
                url=target_url,
                headers=headers,
                data=body or None,
                timeout=TIMEOUT,
            )
        except Exception as exc:  # noqa: PERF203
            payload = {
                "error": "relay_upstream_failed",
                "detail": str(exc),
                "target_url": target_url,
            }
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        content = resp.content or b""
        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() in HOP_HEADERS or k.lower() in RESPONSE_DROP_HEADERS:
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.end_headers()
        if content:
            self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        self._forward("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._forward("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._forward("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self._forward("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward("DELETE")

    def log_message(self, fmt: str, *args) -> None:
        # Keep terminal clean but still visible.
        print(f"[relay] {self.address_string()} - {fmt % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), RelayHandler)
    print(f"[relay] listening on http://{HOST}:{PORT} -> {UPSTREAM_BASE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[relay] stopped")


if __name__ == "__main__":
    main()
