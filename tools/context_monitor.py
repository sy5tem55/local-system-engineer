#!/usr/bin/env python3
"""
context_monitor.py — Live llama.cpp context usage monitor
=========================================================
Polls the llama.cpp /slots and /metrics endpoints and displays
a live terminal dashboard showing token usage, KV cache fill,
and alerts when approaching the degradation threshold.

Usage:
    python3 context_monitor.py [--server http://localhost:8080] [--interval 5]

Requirements:
    pip install requests rich

Dashboard colours:
    Green  = < 50% fill (safe)
    Yellow = 50–70% fill (watch verbosity)
    Orange = 70–85% fill (compaction recommended)
    Red    = > 85% fill (hard reset required)
"""

import argparse
import time
import sys
from datetime import datetime

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, BarColumn, TextColumn
    from rich.live import Live
    from rich.layout import Layout
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("NOTE: 'rich' not installed. Running in plain text mode. Install with: pip install rich\n")


# ─── Configuration ────────────────────────────────────────────────────────────

DEFAULT_SERVER = "http://localhost:8080"
DEFAULT_INTERVAL = 5  # seconds between polls

THRESHOLD_WATCH    = 0.50  # yellow
THRESHOLD_COMPACT  = 0.70  # orange — compaction recommended
THRESHOLD_CRITICAL = 0.85  # red — hard reset required
THRESHOLD_DEGRADE  = 0.92  # model quality severely degraded


# ─── Data Fetching ────────────────────────────────────────────────────────────

def fetch_slots(server_url: str) -> list[dict]:
    """Fetch /slots endpoint. Returns list of slot dicts."""
    try:
        resp = requests.get(f"{server_url}/slots", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return []
    except Exception as e:
        return [{"error": str(e)}]


def fetch_health(server_url: str) -> dict:
    """Fetch /health endpoint."""
    try:
        resp = requests.get(f"{server_url}/health", timeout=5)
        return resp.json()
    except Exception:
        return {"status": "unreachable"}


def fetch_metrics_raw(server_url: str) -> str:
    """Fetch /metrics (Prometheus format). Returns raw text."""
    try:
        resp = requests.get(f"{server_url}/metrics", timeout=5)
        return resp.text
    except Exception:
        return ""


def parse_metric(metrics_text: str, metric_name: str) -> float | None:
    """Extract a single Prometheus metric value by name."""
    for line in metrics_text.splitlines():
        if line.startswith(metric_name) and not line.startswith("#"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return float(parts[-1])
                except ValueError:
                    pass
    return None


# ─── Status Logic ─────────────────────────────────────────────────────────────

def classify_fill(ratio: float) -> tuple[str, str]:
    """Returns (status_label, colour_name) for a fill ratio."""
    if ratio >= THRESHOLD_DEGRADE:
        return "DEGRADED  ", "red"
    elif ratio >= THRESHOLD_CRITICAL:
        return "CRITICAL  ", "red"
    elif ratio >= THRESHOLD_COMPACT:
        return "COMPACT ↑ ", "dark_orange"
    elif ratio >= THRESHOLD_WATCH:
        return "WATCH     ", "yellow"
    else:
        return "OK        ", "green"


def build_advice(ratio: float) -> str:
    """Return actionable advice for the current fill level."""
    if ratio >= THRESHOLD_DEGRADE:
        return "⛔ HARD RESET — model reliability severely degraded. Save state and start new session."
    elif ratio >= THRESHOLD_CRITICAL:
        return "🔴 Perform HARD RESET: write /opt/local-se/session-state.md and start new conversation."
    elif ratio >= THRESHOLD_COMPACT:
        return "🟠 Perform COMPACTION before next tool call. Summarise completed steps."
    elif ratio >= THRESHOLD_WATCH:
        return "🟡 Minimise tool output verbosity. Use grep/head/awk filters aggressively."
    else:
        return "🟢 Context healthy. Normal operation."


# ─── Display: Rich mode ───────────────────────────────────────────────────────

def render_rich(slots: list[dict], health: dict, metrics_text: str, server_url: str) -> Panel:
    """Build a Rich renderable for the live display."""
    console = Console()
    now = datetime.now().strftime("%H:%M:%S")

    # Health row
    health_status = health.get("status", "unknown")
    health_colour = "green" if health_status == "ok" else "red"

    table = Table(
        title=f"[bold]llama.cpp Context Monitor[/bold]  [dim]{server_url}[/dim]  [dim]{now}[/dim]",
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Slot", style="dim", width=5)
    table.add_column("Model", style="white")
    table.add_column("Tokens used", justify="right")
    table.add_column("Context size", justify="right")
    table.add_column("Fill %", justify="right", width=8)
    table.add_column("KV cache", justify="right", width=10)
    table.add_column("Status", width=12)
    table.add_column("Advice")

    if not slots:
        table.add_row(
            "—", "—", "—", "—", "—", "—",
            f"[{health_colour}]{health_status}[/{health_colour}]",
            "No active slots or server unreachable"
        )
    else:
        for slot in slots:
            if "error" in slot:
                table.add_row("ERR", str(slot["error"]), "", "", "", "", "", "")
                continue

            slot_id   = str(slot.get("id", "?"))
            model     = slot.get("model", "unknown")
            if "/" in model:
                model = model.split("/")[-1]
            if len(model) > 35:
                model = model[:32] + "…"

            n_past  = slot.get("n_past", 0)
            n_ctx   = slot.get("n_ctx", 32768)
            ratio   = n_past / n_ctx if n_ctx > 0 else 0.0
            kv_raw  = slot.get("kv_cache_usage_ratio", None)
            kv_str  = f"{kv_raw*100:.1f}%" if kv_raw is not None else "N/A"
            pct_str = f"{ratio*100:.1f}%"

            status_label, colour = classify_fill(ratio)
            advice = build_advice(ratio)

            table.add_row(
                slot_id,
                model,
                f"{n_past:,}",
                f"{n_ctx:,}",
                f"[{colour}]{pct_str}[/{colour}]",
                kv_str,
                f"[{colour}]{status_label}[/{colour}]",
                f"[{colour}]{advice}[/{colour}]",
            )

    # Extra Prometheus metrics if available
    extra_lines = []
    tokens_evaluated = parse_metric(metrics_text, "llamacpp_tokens_evaluated_total")
    if tokens_evaluated is not None:
        extra_lines.append(f"Tokens evaluated (all time): {tokens_evaluated:,.0f}")
    prompt_tokens = parse_metric(metrics_text, "llamacpp_prompt_tokens_total")
    if prompt_tokens is not None:
        extra_lines.append(f"Prompt tokens processed (all time): {prompt_tokens:,.0f}")

    footer = "  |  ".join(extra_lines) if extra_lines else ""

    return Panel(table, subtitle=footer if footer else None)


# ─── Display: Plain text mode ─────────────────────────────────────────────────

def render_plain(slots: list[dict], health: dict, server_url: str) -> None:
    """Print a plain-text status block."""
    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'─'*70}")
    print(f"  llama.cpp Context Monitor  |  {server_url}  |  {now}")
    print(f"  Server health: {health.get('status', 'unknown')}")
    print(f"{'─'*70}")

    if not slots:
        print("  No active slots or server unreachable.")
    else:
        for slot in slots:
            if "error" in slot:
                print(f"  ERROR: {slot['error']}")
                continue
            n_past = slot.get("n_past", 0)
            n_ctx  = slot.get("n_ctx", 32768)
            ratio  = n_past / n_ctx if n_ctx > 0 else 0.0
            pct    = ratio * 100
            kv     = slot.get("kv_cache_usage_ratio", None)
            status_label, _ = classify_fill(ratio)
            bar_filled = int(ratio * 40)
            bar = "█" * bar_filled + "░" * (40 - bar_filled)
            print(f"  Slot {slot.get('id','?')} | {n_past:,}/{n_ctx:,} tokens [{bar}] {pct:.1f}% | {status_label.strip()}")
            if kv is not None:
                print(f"  KV cache: {kv*100:.1f}%")
            print(f"  {build_advice(ratio)}")
    print(f"{'─'*70}")


# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Live llama.cpp context usage monitor")
    parser.add_argument("--server",   default=DEFAULT_SERVER,   help=f"llama-server URL (default: {DEFAULT_SERVER})")
    parser.add_argument("--interval", default=DEFAULT_INTERVAL, type=int, help=f"Poll interval in seconds (default: {DEFAULT_INTERVAL})")
    parser.add_argument("--plain",    action="store_true",      help="Force plain text output (no Rich)")
    args = parser.parse_args()

    use_rich = RICH_AVAILABLE and not args.plain
    server   = args.server.rstrip("/")

    print(f"Monitoring {server} — polling every {args.interval}s. Press Ctrl+C to stop.")

    if use_rich:
        console = Console()
        with Live(console=console, refresh_per_second=0.5, screen=False) as live:
            while True:
                slots        = fetch_slots(server)
                health       = fetch_health(server)
                metrics_text = fetch_metrics_raw(server)
                live.update(render_rich(slots, health, metrics_text, server))
                time.sleep(args.interval)
    else:
        while True:
            slots  = fetch_slots(server)
            health = fetch_health(server)
            render_plain(slots, health, server)
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
