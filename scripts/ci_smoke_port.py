#!/usr/bin/env python3
"""Allocate a fresh loopback port for a self-contained CI smoke server.

Prevents the original 127.0.0.1:7777 CI replay from testing an unrelated
authorised process. This changes no authentication or actual smoke assertions.
"""
from __future__ import annotations

import os
import socket
from pathlib import Path


def unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def export_to_github_env(env_path: str) -> int:
    if not env_path:
        raise ValueError("GITHUB_ENV must be provided by the CI runner")
    port = unused_loopback_port()
    with Path(env_path).open("a", encoding="utf-8") as stream:
        stream.write(f"TAO_SMOKE_PORT={port}\n")
    return port


def main() -> None:
    port = export_to_github_env(os.environ.get("GITHUB_ENV", ""))
    print(f"Allocated isolated loopback smoke port {port}")


if __name__ == "__main__":
    main()
