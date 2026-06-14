# Rebuild spec — node-t3-003 / node-t3-004 as valid actuation challenges

> Authored: P29 Cowork (2026-06-14). Apply from WSL2 (edit the two seed scripts, re-run them,
> then `freeze_bench.py --force` will pick them up). Seeds:
> `scripts/seed_node_t3_llama_cutover.py` (003) · `scripts/seed_node_t3_llama_model_path.py` (004).

## Why they were bench-invalid

`freeze_bench.py` accepts a write-mode challenge only if **every assertion is `verify_ssh`-backed
AND the challenge carries an `actuation` block**. Both seeds have `verify_ssh` on every assertion
but **neither has an `actuation` block** — so the harness never executed the model's commands; the
"solve" was the pre-existing world state, not the model. That is the exact defect 1.7.0-a fixes.

## Decision inputs (P29)

- **ctx-size canon = 81920** for both LUCIFER (4090) and node3090 — confirmed (SY5). The seeds
  already assert 81920; no change to that value.
- **socat is gone.** P27 eliminated `hermes-socat` / `:8643`; the gateway binds `0.0.0.0:8642`
  directly. t3-003's `a4` still checks socat `:8643` — must move to `:8642` direct.
- **The gate blocks raw nohup.** `nohup /usr/local/bin/llama-server … > /home/lse-admin/…` is
  rejected by the actuation gate: the line contains a privileged path (`/usr/`) **and** a write op
  (`>`), tripping the privileged-write rule (a false positive — the redirect targets `/home` — but
  the validated 16/16 gate behaves this way and we are not loosening it). Verified against
  `actuation.gate_command()`. The **only gate-clean normalize path is a managed restart**:
  `sudo systemctl restart llama-server` passes when allowlisted.

## Prerequisite (confirm before relying on this in a run)

node3090 must have a **`llama-server` systemd unit** whose `ExecStart` carries the canonical flags
(`--ctx-size 81920 --n-gpu-layers 129 --cache-type-k q8_0 --model <canonical path> --host 0.0.0.0
--port 8080 --flash-attn on …`), so a `systemctl restart` yields canonical state and the flags show
in `pgrep -af llama-server` (which the assertions parse). This aligns with the documented node5090
pattern (env file + unit). If node3090 instead exposes a **gate-clean `/opt` launch script**
(`/opt` is not a privileged-write path), substitute that command in the one constant below — no
other change.

## Change set — node-t3-003 (`seed_node_t3_llama_cutover.py`)

**1. Add an `actuation` block** as the first key of the `success_criteria` dict (before
`"assertions"`):

```python
"actuation": {
    "host": "192.168.5.41",
    "user": "lse-admin",
    # Managed restart is the only gate-clean path (raw nohup /usr/local/bin/llama-server
    # is blocked: /usr/ + redirect). If node3090 starts llama.cpp another managed way
    # (e.g. an /opt launch script), change these prefixes to match — one place.
    "allow_sudo": [
        "sudo systemctl restart llama-server",
        "sudo systemctl start llama-server",
        "sudo systemctl stop llama-server",
        "sudo systemctl status llama-server",
    ],
    "timeout": 240,   # systemctl restart + 27B model load (+ in-block health poll)
},
```

**2. Rewrite assertion `a4`** — drop socat, verify the gateway on `:8642` direct:

```python
{
    "id": "a4",
    "points": 1,
    "code": "assert hermes_gateway_active is True and gateway_listening is True",
    "description": (
        "Hermes gateway active (hermes-gateway.service) and listening directly on "
        "0.0.0.0:8642 — confirms the LSE→Hermes call path post-restart. "
        "(socat :8643 eliminated P27; gateway binds :8642 direct.)"
    ),
    "verify_ssh": {
        "host": "192.168.5.41", "user": "lse-admin",
        "cmd": (
            "systemctl is-active hermes-gateway 2>/dev/null; "
            "echo '---'; ss -tlnp | grep ':8642' | wc -l"
        ),
        "parse": (
            "_parts = stdout.strip().split('---'); "
            "hermes_gateway_active = _parts[0].strip() == 'active' if _parts else False; "
            "_n = _parts[1].strip() if len(_parts) > 1 else '0'; "
            "gateway_listening = _n.isdigit() and int(_n) > 0"
        ),
    },
},
```

**3. `starting_state`** — `hermes_url` `:8643` → `:8642`. Replace the "Step 4a stop / 4b nohup
start" notes with: *"Step 4 — normalise via the managed service (gate-clean):
`ssh lse-admin@192.168.5.41 "sudo systemctl restart llama-server"`. The unit's ExecStart carries
the canonical flags. A raw `nohup /usr/local/bin/llama-server …` start is BLOCKED by the gate."*
Keep the "no `call_hermes` between restart and health-ok" rule.

**4. `failure_modes`** — drop socat from `3/4` and `4/4`:
- `3/4`: "llama-server healthy but Hermes gateway not active or not listening on :8642 (call path broken)."
- `4/4`: "llama-server at canonical state (ctx-size 81920, n-gpu-layers 129, q8_0 cache, health ok) and Hermes gateway verified on :8642 direct."

**5. Docstring** — replace the "a4 verifies … socat" change-note with the P29 rebuild note
(actuation added; a4 → :8642 direct; managed restart via allow_sudo).

## Change set — node-t3-004 (`seed_node_t3_llama_model_path.py`)

Simpler — t3-004 has **no socat assertion** (its `a4` is just `health_ok`). Only one structural
change is required:

**1. Add the same `actuation` block** (identical to above) as the first key of `success_criteria`.

**2. `starting_state` notes** — replace the "Step 4a stop / 4b nohup start" block with the managed
`sudo systemctl restart llama-server`, same as 003. The canonical **model path** still differs from
the running one, so the systemd unit's `ExecStart` must already point at the canonical model
(`/home/sy5/.lmstudio/…`) for the restart to satisfy `a1` — i.e. this challenge presumes the fix is
"unit is correct, process is stale, restart to apply." If instead the intent is for the model to
*edit the unit/env file then restart*, add `/etc/...`-write entries to `allow_sudo` and an assertion
that reads the unit file. (Flag — confirm which framing you want.)

## After editing

```bash
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
python3 -c "import ast; ast.parse(open('scripts/seed_node_t3_llama_cutover.py').read()); ast.parse(open('scripts/seed_node_t3_llama_model_path.py').read()); print('ast OK')"
python3 scripts/seed_node_t3_llama_cutover.py      # re-seed 003
python3 scripts/seed_node_t3_llama_model_path.py   # re-seed 004
python3 scripts/freeze_bench.py --name lse-bench-v1 --force   # now includes 003/004 if valid
```
