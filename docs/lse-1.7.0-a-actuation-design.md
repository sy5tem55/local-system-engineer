# LSE 1.7.0-a — Episode Actuation Layer (design + deploy)

> Status: IMPLEMENTED (P28 Cowork, 2026-06-13) — code compile-verified, awaiting live test on LUCIFER.
> Files: `scripts/actuation.py` (NEW, 266 lines) · `scripts/lse_challenge_env.py` (592 → 655, +63)

## Problem

The episode harness never executed model-emitted commands. `LSEChallengeEnv.step()`
parsed the model's ` ```json ` findings block, and `verify_ssh` read ground-truth
world state. For **read** challenges this works (model reports a value, `verify_ssh`
confirms it). For **write** challenges it is structurally broken: nothing the model
emits ever changes the world, so `verify_ssh` always reads the unchanged world and the
challenge passes only if it was already fixed (e.g. node-t3-004 "solved" via the
interactive LSE session, not the episode). The benchmark measured **world state, not
the model** — making every write-mode result meaningless. Root cause confirmed P20.

## Design

A new actuation step sits between "model responds" and "assertions evaluate":

```
step(action)
  └─ _actuate(action)            ← NEW: extract ```bash block → gate → SSH execute
  └─ _evaluate_assertions(action, actuation)
        └─ verify_ssh            ← now reads the world the model actually changed
```

### Decisions

1. **Opt-in, backward-compatible.** A challenge's `success_criteria` JSON may carry a
   top-level `actuation` object. Absent ⇒ `_actuate()` returns `None` and behavior is
   byte-identical to today. All 24 existing challenges are unaffected (verified).
2. **Output contract.** When `actuation` is present, `_build_challenge_prompt` appends an
   ACTUATION instruction telling the model to emit a ` ```bash ` block of commands
   alongside its ` ```json ` findings block.
3. **Pipeline order.** Extract bash block → gate **every** line → execute the whole block
   in **one** SSH session (`bash -s`, `set -e`) so `cd`/env persist and the first failure
   aborts → then evaluate assertions.
4. **Safety gates ported verbatim** from Cogitator `execute_command` v1.7.14:
   - `_BLOCKED_COMMANDS` — disk destruction, `rm -rf` (all flag orders), fork bomb,
     `userdel`/`groupdel`, `passwd`/`visudo`, `iptables -F`, `of=/dev/`, etc. **No override.**
   - `_PRIVILEGED_PREFIXES` (`sudo `/`su `/`doas `) blocked **anywhere** in the line
     (substring check catches pipelines) — overridable only by per-challenge `allow_sudo`.
   - Privileged-path write (`/etc /usr /boot /sys /proc /mnt` + a write op) blocked unless
     in `allow_sudo`.
   - **Fail-closed:** one gate violation rejects the entire block (no partial fixes).
5. **`allow_sudo` allowlist** — real sysadmin fixes need `sudo systemctl restart …`.
   Default is deny; each write challenge declares an exact-prefix allowlist of the
   privileged commands its solution legitimately requires.
6. **Assertion namespace** gains `actuation_stdout`, `actuation_stderr`, `actuation_exit`,
   `actuation_ran` so assertions can check command output directly, in addition to
   `verify_ssh` world reads (which remain the authoritative ground truth).

## New challenge schema (`success_criteria`)

```json
{
  "actuation": {
    "host": "node3090.home.arpa",
    "user": "lse-admin",
    "allow_sudo": ["sudo systemctl restart llama-server"],
    "timeout": 60
  },
  "assertions": [
    {
      "id": "A1",
      "description": "Duplicate model file removed; exactly one copy remains",
      "verify_ssh": {
        "host": "node3090.home.arpa",
        "user": "lse-admin",
        "cmd": "ls /opt/models/*.gguf | wc -l",
        "parse": "gguf_count = int(stdout)"
      },
      "code": "assert gguf_count == 18"
    }
  ]
}
```

`allow_sudo` entries are matched as exact line prefixes. The hard `_BLOCKED_COMMANDS`
list can never be allowlisted.

## Remaining 1.7.0-a work (not yet done)

- [ ] `run_episode.py` `--eval --no-learn` flag — gate `LeaderboardService.record_episode`
      and `ChallengeGenerator.process_episode` so benchmark runs don't mutate learning state.
- [ ] Freeze `lse-bench-v1` — tag the frozen challenge set; add `verify_ssh` to all bench
      challenges so every result is ground-truth.
- [ ] Author the first real write challenge (`node-t3-006` Model Store Reconciliation) using
      the schema above and run it as the actuation smoke test.
- [ ] Record Condition A baseline (current model, frozen suite, learning off).

## Deploy / test on LUCIFER (WSL2)

```bash
cd /mnt/c/Users/SY5/Claude/Projects/local-system-engineer
# 1. Module self-test (no SSH, no model)
python3 scripts/actuation.py
# 2. Env still imports and read-only path unchanged
python3 -c "import sys; sys.path.insert(0,'scripts'); import lse_challenge_env; print('env OK')"
# 3. Existing read-only regression — must behave exactly as before
python3 scripts/run_episode.py --challenge pf-t1-001 --dry-run
python3 scripts/run_episode.py --challenge pf-t1-001
# 4. After seeding a write challenge with an "actuation" block, run it:
#    python3 scripts/run_episode.py --challenge node-t3-006
```

Commit from WSL2/PowerShell (sandbox git is unreliable — stale NTFS mount):
`git add scripts/actuation.py scripts/lse_challenge_env.py docs/lse-1.7.0-a-actuation-design.md`
