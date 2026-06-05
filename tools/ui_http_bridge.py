#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import socketserver
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlparse


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}

DIRECT_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_target(base: str, path: str) -> str:
    base = base.rstrip("/") + "/"
    if path.startswith("/"):
        path = path[1:]
    return urljoin(base, path)


class ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._proxy()

    def do_POST(self):
        self._proxy()

    def do_PUT(self):
        self._proxy()

    def do_DELETE(self):
        self._proxy()

    def do_OPTIONS(self):
        self._proxy()

    def _proxy(self):
        target_base = self.server.target_base  # type: ignore[attr-defined]
        timeout = self.server.timeout_s  # type: ignore[attr-defined]

        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None
        target_url = build_target(target_base, self.path)

        headers = {}
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP:
                continue
            headers[k] = v

        req = urllib.request.Request(
            target_url,
            data=body,
            method=self.command,
            headers=headers,
        )

        start = time.monotonic()
        try:
            with DIRECT_OPENER.open(req, timeout=timeout) as resp:
                data = resp.read()
                self.send_response(resp.status)
                for k, v in resp.headers.items():
                    if k.lower() in HOP_BY_HOP:
                        continue
                    if k.lower() == "transfer-encoding":
                        continue
                    if k.lower() == "content-length":
                        continue
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if data:
                    self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read() if hasattr(e, "read") else b""
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)
        except Exception as e:
            elapsed = time.monotonic() - start
            msg = f"proxy error after {elapsed:.2f}s: {e}".encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

    def log_message(self, fmt: str, *args):
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        sys.stdout.write("%s - - [%s] %s\n" % (self.client_address[0], self.log_date_time_string(), fmt % args))
        sys.stdout.flush()


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def get_local_ips() -> list[str]:
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None):
            if info[0] == socket.AF_INET:
                ips.add(info[4][0])
    except Exception:
        pass
    return sorted(ips)


def get_windows_adapter_ips() -> list[tuple[str, str]]:
    ps = (
        "Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -notlike '127.*' -and $_.AddressState -eq 'Preferred' } | "
        "Select-Object IPAddress,InterfaceAlias | "
        "ConvertTo-Json -Compress"
    )
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return []
    if not out:
        return []
    try:
        data = json.loads(out)
    except Exception:
        return []
    rows = data if isinstance(data, list) else [data]
    found: list[tuple[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ip = str(row.get("IPAddress", "")).strip()
        alias = str(row.get("InterfaceAlias", "")).strip()
        if ip and not ip.startswith("127."):
            found.append((ip, alias or "unknown"))
    return sorted(found)


def main() -> int:
    ap = argparse.ArgumentParser(description="Simple HTTP bridge to expose UI API to LAN.")
    ap.add_argument("--listen-host", default="0.0.0.0")
    ap.add_argument("--listen-port", type=int, default=8080)
    ap.add_argument("--target", default="http://127.0.0.1:18080")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--duration", type=float, default=0.0, help="Auto-stop after N seconds (0 = run until Ctrl+C).")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    parsed = urlparse(args.target)
    if not parsed.scheme or not parsed.netloc:
        print(f"ERROR: bad --target {args.target}", flush=True)
        return 2
    no_proxy = "127.0.0.1,localhost,::1"
    os.environ["NO_PROXY"] = no_proxy
    os.environ["no_proxy"] = no_proxy

    server = ThreadingHTTPServer((args.listen_host, args.listen_port), ProxyHandler)
    server.target_base = args.target  # type: ignore[attr-defined]
    server.timeout_s = args.timeout  # type: ignore[attr-defined]
    server.quiet = args.quiet  # type: ignore[attr-defined]
    server.timeout = 0.2

    ips = get_local_ips()
    print(
        f"START bridge listen http://{args.listen_host}:{args.listen_port} -> {args.target}",
        flush=True,
    )
    if ips:
        for ip in ips:
            print(f"LAN URL: http://{ip}:{args.listen_port}", flush=True)
    adapters = get_windows_adapter_ips()
    if adapters:
        print("Windows adapter URLs (choose the Ethernet/LAN interface connected to the Wi-Fi AP):", flush=True)
        for ip, alias in adapters:
            print(f"  {alias}: http://{ip}:{args.listen_port}", flush=True)
    print("VPN/proxy guard: target requests use a direct no-proxy opener.", flush=True)

    if args.duration > 0:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            server.handle_request()
        print("DONE (duration elapsed)", flush=True)
        return 0

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("STOP", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
