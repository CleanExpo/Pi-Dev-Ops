"""Background supervisor for the Mission Control Model Fabric.

Runs after Pi-CEO startup has already been released to Railway. This process
may spend time configuring providers without blocking the API healthcheck. If
the sidecar becomes healthy it stays attached and waits on the OmniRoute child;
if setup fails, Pi-CEO keeps serving via its direct high-trust provider path.
"""
from __future__ import annotations

import logging
import os

from scripts.runtime_model_guard import start_model_fabric


def main() -> int:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    proc = start_model_fabric()
    if proc is None:
        return 0
    try:
        return int(proc.wait())
    except KeyboardInterrupt:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
