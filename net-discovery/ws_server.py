"""
ws_server.py — Network Observability WebSocket broadcast server
Watches snapshot.json and pushes the full payload to all connected browsers.

PRE-INSTALL RULE: Check before installing.
  Check: pip show websockets
  Install only if missing: pip install websockets --break-system-packages
  (wsproto==1.3.2 is installed but it's a codec only — not a server)

Behaviour:
  - Polls snapshot.json every POLL_INTERVAL seconds for mtime changes.
  - On change: broadcasts full JSON to all connected clients.
  - On new connection: immediately sends current snapshot (no waiting for next cycle).
  - Clients that disconnect mid-send are removed silently.

index.html connects to ws://localhost:8765 (NETOBS_WS_PORT env var overrides port).

Usage:
  python3 ws_server.py [--config config.json] [--port 8765]

Stop:  Ctrl+C

Run alongside discovery engine:
  python3 discovery_engine.py &
  python3 ws_server.py &
  python3 prometheus_exporter.py &
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------
def _check_pkg(name: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(name) is not None


if not _check_pkg("websockets"):
    print(
        "ERROR: 'websockets' library not importable.\n"
        "Check first : pip show websockets\n"
        "Install only if missing: pip install websockets --break-system-packages",
        file=sys.stderr,
    )
    sys.exit(1)

import websockets
from websockets.server import WebSocketServerProtocol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("netobs.ws")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_SNAPSHOT = Path(__file__).parent / "snapshot.json"
DEFAULT_PORT = 8765
POLL_INTERVAL = 1.0  # seconds between mtime checks


# ---------------------------------------------------------------------------
# Server state
# ---------------------------------------------------------------------------
class BroadcastServer:
    def __init__(self, snapshot_path: Path, port: int) -> None:
        self.snapshot_path = snapshot_path
        self.port = port
        self._clients: set[WebSocketServerProtocol] = set()
        self._last_mtime: float = 0.0
        self._last_payload: Optional[str] = None

    # ------------------------------------------------------------------
    async def handler(self, ws: WebSocketServerProtocol) -> None:
        """Handle a new WebSocket connection."""
        remote = ws.remote_address
        log.info("Client connected: %s (total: %d)", remote, len(self._clients) + 1)
        self._clients.add(ws)

        # Send current snapshot immediately on connect
        if self._last_payload:
            try:
                await ws.send(self._last_payload)
            except websockets.ConnectionClosed:
                pass

        try:
            # Keep connection alive; we're push-only so just wait for close.
            await ws.wait_closed()
        finally:
            self._clients.discard(ws)
            log.info("Client disconnected: %s (total: %d)", remote, len(self._clients))

    # ------------------------------------------------------------------
    async def _watcher(self) -> None:
        """Poll snapshot.json for mtime changes and broadcast on update."""
        log.info("Watching %s (poll interval: %.1fs)", self.snapshot_path, POLL_INTERVAL)
        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                mtime = self.snapshot_path.stat().st_mtime
            except FileNotFoundError:
                continue

            if mtime <= self._last_mtime:
                continue

            self._last_mtime = mtime
            payload = self._read_snapshot()
            if payload is None:
                continue

            self._last_payload = payload
            if not self._clients:
                continue

            log.info(
                "Snapshot updated — broadcasting to %d client(s)",
                len(self._clients),
            )
            await self._broadcast(payload)

    # ------------------------------------------------------------------
    async def _broadcast(self, payload: str) -> None:
        """Send payload to all connected clients; remove dead ones."""
        dead: set[WebSocketServerProtocol] = set()
        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except websockets.ConnectionClosed:
                dead.add(ws)
            except Exception as exc:
                log.warning("Send error to %s: %s", ws.remote_address, exc)
                dead.add(ws)
        self._clients -= dead

    # ------------------------------------------------------------------
    def _read_snapshot(self) -> Optional[str]:
        try:
            raw = self.snapshot_path.read_text(encoding="utf-8")
            # Validate it's parseable JSON before broadcasting
            json.loads(raw)
            return raw
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            log.warning("snapshot.json parse error (skipping broadcast): %s", exc)
            return None
        except OSError as exc:
            log.warning("snapshot.json read error: %s", exc)
            return None

    # ------------------------------------------------------------------
    async def run(self) -> None:
        # Pre-load snapshot so first connecting client gets data immediately
        if self.snapshot_path.exists():
            self._last_mtime = self.snapshot_path.stat().st_mtime
            self._last_payload = self._read_snapshot()
            if self._last_payload:
                log.info("Loaded existing snapshot (%d bytes)", len(self._last_payload))

        log.info("WebSocket server starting on ws://0.0.0.0:%d", self.port)

        async with websockets.serve(self.handler, "0.0.0.0", self.port):
            log.info("Listening — index.html connects to ws://localhost:%d", self.port)
            await self._watcher()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _load_config(config_path: Path) -> dict:
    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as exc:
        log.warning("Could not read config.json (%s) — using defaults", exc)
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Network Observability WebSocket broadcast server"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).parent / "config.json",
        help="Path to config.json",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="Path to snapshot.json (overrides config output.snapshot_file)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="WebSocket port (overrides config services.ws_port)",
    )
    args = parser.parse_args()

    cfg = _load_config(args.config)

    # Resolve snapshot path: CLI > config > default
    if args.snapshot:
        snapshot_path = args.snapshot
    else:
        snap_rel = cfg.get("output", {}).get("snapshot_file", "snapshot.json")
        snapshot_path = args.config.parent / snap_rel

    # Resolve port: CLI > env > config > default
    port = (
        args.port
        or int(os.environ.get("NETOBS_WS_PORT", 0))
        or cfg.get("services", {}).get("ws_port", DEFAULT_PORT)
    )

    server = BroadcastServer(snapshot_path, port)
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        log.info("WebSocket server stopped.")


if __name__ == "__main__":
    main()
