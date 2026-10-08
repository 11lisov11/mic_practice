#!/usr/bin/env python3
"""Perform one HTTP request from WSL to a LAN HMI; request arrives on stdin."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def request_once(request_data: dict) -> dict:
    response_format = request_data.get("response_format", "json")
    if response_format not in ("json", "text"):
        raise ValueError("Unsupported response format")
    method = request_data["method"]
    url = request_data["url"]
    headers = request_data["headers"]
    body = request_data.get("body")
    payload = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=8.0) as response:
            code, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        code, raw = exc.code, exc.read()
    result = raw.decode("utf-8") if response_format == "text" else (json.loads(raw) if raw else {})
    return {"code": code, "payload": result}


def main() -> int:
    for line in sys.stdin:
        try:
            result = request_once(json.loads(line))
        except Exception as exc:
            result = {"error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
