"""Session-wide pytest setup.

SPEC-cycle-completes-2026-08 §8 item 5: `~/.local/bin` (where the node
symlink -- ~/.local/bin/node -> ~/.hermes/node/bin/node -- lives on this
host) is absent from the minimal PATH pytest inherits under nohup/cron-like
invocation, so tests/test_ui_router.py's `test_extracted_dashboard_js_is_
syntactically_valid` -- which shells out to `node --check` as a real parse
of the extracted dashboard JS (SPEC test 7) -- could not find node and
skipped instead of running. Prepending it here, once, at collection time,
lets that test run for real instead of skipping.

This only affects `os.environ["PATH"]` for the pytest process (and anything
it subprocesses, such as the node --check call above) -- it does not touch
any node3090/llama-server node profile or launch flag.
"""
import os

_LOCAL_BIN = os.path.expanduser("~/.local/bin")
_path_entries = os.environ.get("PATH", "").split(os.pathsep)
if _LOCAL_BIN not in _path_entries:
    os.environ["PATH"] = os.pathsep.join([_LOCAL_BIN, *_path_entries])
