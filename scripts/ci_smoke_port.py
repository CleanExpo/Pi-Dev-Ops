#!/usr/bin/env python3
"""Allocate and identify an isolated, test-only Pi CEO HTTP smoke instance.

A free port alone proves nothing: a foreign listener can claim it before uvicorn.
An unpredictable instance marker on uvicorn responses prevents false readiness.
"""
from __future__ import annotations

import os
import secrets
import socket
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

HEADER = "X-SDA-Smoke-Instance"


def unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def new_instance() -> tuple[int, str]:
    return unused_loopback_port(), secrets.token_hex(16)


def matches_server(port: int, nonce: str) -> bool:
    if not (1 <= port <= 65535 and nonce):
        return False
    try:
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=1.0) as response:
            return response.status == 200 and response.headers.get(HEADER) == nonce
    except (URLError, OSError, ValueError):
        return False


def export_to_github_env(env_path: str) -> tuple[int, str]:
    if not env_path:
        raise ValueError("GITHUB_ENV must be provided by the CI runner")
    port, nonce = new_instance()
    with Path(env_path).open("a", encoding="utf-8") as stream:
        stream.write(f"TAO_SMOKE_PORT={port}\nTAO_SMOKE_NONCE={nonce}\n")
    return port, nonce


def main() -> None:
    args = sys.argv[1:]
    if args == ["--emit-shell"]:
        port, nonce = new_instance()
        print(f"{port} {nonce}")
    elif len(args) == 3 and args[0] == "--check":
        try:
            port = int(args[1])
        except ValueError:
            raise SystemExit(2) from None
        raise SystemExit(0 if matches_server(port, args[2]) else 1)
    elif args:
        raise SystemExit("usage: ci_smoke_port.py [--emit-shell | --check PORT NONCE]")
    else:
        port, _ = export_to_github_env(os.environ.get("GITHUB_ENV", ""))
        print(f"Allocated isolated loopback smoke port {port}")


if __name__ == "__main__":
    main()
