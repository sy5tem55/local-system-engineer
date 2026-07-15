"""Regression checks for the production gateway launcher."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "tools" / "start-goethe.sh"


def test_gateway_launch_is_detached_before_health_checks():
    text = SCRIPT.read_text(encoding="utf-8")
    launch = text.index("setsid nohup")
    background = text.index('>"$LOG" 2>&1 &', launch)
    health = text.index("Step 5: verify", background)

    assert launch < background < health
    assert "</dev/null" in text[launch:background]
    assert 'GOETHE_EMBED_MODEL="qwen3-embedding:0.6b"' in text


def test_gateway_launcher_records_real_bound_process():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'COUNT=$(pgrep -cf "$PAT" || true)' in text
    assert 'REAL_PID=$(pgrep -f "$PAT")' in text
    assert 'echo "$REAL_PID" > "$PIDFILE"' in text
