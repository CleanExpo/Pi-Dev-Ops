"""Serve a local Excalidraw board for the UG-N intent catalog.

Usage:
  python scripts/serve_intent_excalidraw.py --port 7119
"""
from __future__ import annotations

import argparse
import json
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app.server.youtube_intent import build_excalidraw_nodes, load_state


def _is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _build_elements(payload: dict) -> list[dict]:
    status = payload.get("status", {})
    metrics = payload.get("metrics", {})
    nodes = [
        ("signalSources", "Signal Sources", 80, 80),
        ("relevanceFilter", "Relevance Filter", 420, 80),
        ("personaModel", "Persona Model", 760, 80),
        ("verticalPathways", "Vertical Pathways", 760, 300),
        ("wikiOutputs", "Wiki Outputs", 420, 300),
    ]
    colors = {"new": "#f59e0b", "validated": "#16a34a", "needs_review": "#dc2626"}
    elements: list[dict] = []
    for idx, (key, label, x, y) in enumerate(nodes):
        state = status.get(key, "new")
        elements.append(
            {
                "id": f"box-{idx}",
                "type": "rectangle",
                "x": x,
                "y": y,
                "width": 220,
                "height": 90,
                "strokeColor": colors.get(state, "#334155"),
                "backgroundColor": "#ffffff",
                "roughness": 0,
                "strokeWidth": 2,
                "opacity": 100,
                "seed": 2000 + idx,
                "version": 1,
                "versionNonce": 4000 + idx,
                "isDeleted": False,
            }
        )
        elements.append(
            {
                "id": f"text-{idx}",
                "type": "text",
                "x": x + 16,
                "y": y + 18,
                "width": 180,
                "height": 48,
                "text": f"{label}\\n[{state}]",
                "fontSize": 20,
                "fontFamily": 1,
                "textAlign": "left",
                "verticalAlign": "top",
                "strokeColor": "#111827",
                "backgroundColor": "transparent",
                "roughness": 0,
                "strokeWidth": 1,
                "opacity": 100,
                "seed": 3000 + idx,
                "version": 1,
                "versionNonce": 5000 + idx,
                "isDeleted": False,
            }
        )

    metric_text = (
        f"accepted={metrics.get('acceptedSignals', 0)}\\n"
        f"excluded={metrics.get('excludedSignals', 0)}\\n"
        f"topics={metrics.get('topics', 0)}\\n"
        f"traits={metrics.get('personaTraits', 0)}\\n"
        f"verticals={metrics.get('verticalSignals', 0)}"
    )
    elements.append(
        {
            "id": "metrics",
            "type": "text",
            "x": 80,
            "y": 300,
            "width": 220,
            "height": 120,
            "text": metric_text,
            "fontSize": 18,
            "fontFamily": 3,
            "textAlign": "left",
            "verticalAlign": "top",
            "strokeColor": "#0f172a",
            "backgroundColor": "transparent",
            "roughness": 0,
            "strokeWidth": 1,
            "opacity": 100,
            "seed": 9991,
            "version": 1,
            "versionNonce": 9992,
            "isDeleted": False,
        }
    )
    return elements


def _html() -> str:
    return """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>UG-N Intent Board</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      html, body, #root { margin: 0; width: 100%; height: 100%; overflow: hidden; }
      .toolbar { position: fixed; top: 8px; left: 8px; z-index: 1000; background: #fff; border: 1px solid #d4d4d8; border-radius: 6px; padding: 6px 10px; font: 13px sans-serif; }
      .toolbar button { margin-left: 8px; }
    </style>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
    <script src="https://unpkg.com/@excalidraw/excalidraw/dist/excalidraw.production.min.js"></script>
  </head>
  <body>
    <div class="toolbar">UG-N Intent Excalidraw <button id="refresh">Refresh from catalog</button></div>
    <div id="root"></div>
    <script>
      const { Excalidraw } = window.ExcalidrawLib;
      const initial = { appState: { viewBackgroundColor: '#f8fafc' }, elements: [] };
      let excalApi = null;
      async function loadBoard() {
        const res = await fetch('/board-state', { cache: 'no-store' });
        const data = await res.json();
        if (excalApi) excalApi.updateScene({ elements: data.elements, appState: initial.appState });
      }
      function App() {
        return React.createElement(Excalidraw, {
          initialData: initial,
          excalidrawAPI: (api) => { excalApi = api; loadBoard(); },
        });
      }
      ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
      document.getElementById('refresh').addEventListener('click', loadBoard);
    </script>
  </body>
</html>"""


class BoardHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in ("/", "/index.html"):
            body = _html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/board-state":
            payload = build_excalidraw_nodes(load_state())
            self._send_json({"elements": _build_elements(payload), **payload})
            return
        self.send_response(404)
        self.end_headers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve UG-N intent Excalidraw board")
    parser.add_argument("--port", type=int, default=7119)
    args = parser.parse_args()

    if not _is_port_free(args.port):
        print(f"Port {args.port} is not free. Choose another port or stop the existing server.")
        return 1

    Path(".harness/ugn_intent_youtube").mkdir(parents=True, exist_ok=True)
    server = HTTPServer(("127.0.0.1", args.port), BoardHandler)
    print(f"UG-N intent Excalidraw board at http://localhost:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
