# Report — node facts, model inventory, and profile matcher (Layer 0+1)

Implements `docs/SPEC-node-facts-and-profile-matcher-2026-08.md` on
`codex/fix-sudo-grants-live`. Read-only throughout: nothing started,
stopped, or written to engine config; nothing fetched from the web;
`_NODE_REGISTRY` and `goethe_node.py` untouched.

## What changed

- **`tools/node_facts.py`** (new, ~460 lines). Implements:
  - `collect_hardware(node)` — GPU/CPU/RAM/host facts. `node4090` (LUCIFER)
    probed locally via `nvidia-smi`/`lscpu`/`free`/`hostname`/`uname`.
    Remote nodes (`node3090`, `node5090`, looked up from
    `goethe_node.NodeLifecycleMixin._NODE_REGISTRY`, imported read-only) are
    probed with one combined SSH command (`ConnectTimeout=5`,
    `BatchMode=yes` — no Wake-on-LAN, so a sleeping node is never woken).
    An unreachable node returns `host.reachable: False` with `gpu`/`cpu`/
    `ram` all `null` and `source: "unreachable"` — never zeroed hardware.
    Each GPU carries `vram_bandwidth_gbps: null, bandwidth_source:
    "not-probed"` — it's a published spec, not a probe, so it is left for
    Layer 2's web research rather than guessed.
  - `collect_models(roots)` — enumerates `*.gguf` under
    `/home/sy5/models` and `/opt/local-se/nas/Models` (see ground-truth
    correction below), recording path/size/mtime/quant-from-filename only
    (no hashing, no opening file contents). An unreachable root is
    `reachable: False, files: []`, never an exception.
  - `parse_profile(path)` / `list_profiles(dir)` — parses the four
    canonical `<ROLE>-<model>.gguf.md` llama-server invocations under
    `/mnt/c/Goethe3.0/`, handling both the UTF-8-BOM files and the one
    CRLF-without-BOM file, backslash-newline shell continuations, and
    quoted values (e.g. the `--chat-template-kwargs` JSON string).
  - `classify_flag(flag)` — the Hazard A fix: flags are `identity` /
    `hardware` / `deployment`, matching the spec §3 table exactly
    (`--host`/`--port`/`--path`/`--log-file`/`--slot-save-path` =
    deployment; `--threads`/`--threads-batch`/`-ngl`/`--batch-size`/
    `--ubatch-size` = hardware; everything else, including anything
    unrecognized, defaults to identity).
  - `match_live(profiles, live_pid, live_flags=None)` — the Hazard B fix:
    ranks every known profile against the live process (by identity-flag
    agreement, most-agreeing first) rather than validating one file, and
    reports `verdict: "exact" | "closest" | "none"` plus the full
    identity/hardware/deployment diff for each ranked profile.
  - CLI: `--hardware [--node NAME]`, `--models`, `--match [--profile-dir
    DIR]`, `--all`; human-readable by default, `--json` for machine
    consumption.
- **`tests/test_node_facts.py`** (new, 15 assertions across the 8 named
  cases from spec §6).
- Both files copied to the Windows mirror
  (`/mnt/c/Users/SY5/Claude/Projects/local-system-engineer/{tools,tests}/`)
  and verified byte-identical via `sha256sum`, per §9 housekeeping (the
  module isn't on the mirror's watched list, but the mirror is a full repo
  copy).
- Committed on `codex/fix-sudo-grants-live` via `git commit -F <file>`
  (commit `24391cb`). Not pushed.

## Ruff — before / after

- `tools/node_facts.py` + `tests/test_node_facts.py` alone:
  **0 findings** both before writing (trivially, files didn't exist) and
  after (one `F401` unused-`pytest`-import was caught and fixed during
  development; final state is clean).
- Full tree (`ruff check .`): **229 pre-existing errors**, all in files
  this task did not touch. `grep -c node_facts` against that output is
  **0** — none of the 229 are attributable to the new files.

## Tests — before / after

- Baseline (spec §2, pre-existing): **728 passed**.
- After adding `tests/test_node_facts.py`: **743 passed**, 0 failed, 0
  skipped, backgrounded run completed in 84.26s. 743 − 728 = 15, exactly
  the new test count — no regressions anywhere else in the suite.

## Break-and-restore — tests 2 and 6 (load-bearing)

**Test 2 — deployment differences never produce drift (Hazard A).**
Broke it by removing `"--host"` from `DEPLOYMENT_FLAGS` (sed on line 71).
Result, red:

```
> assert result["verdict"] == "exact"
E AssertionError: assert 'closest' == 'exact'
E   - exact
E   + closest
1 failed in 0.03s
```

Restored from a pre-edit backup (`diff` against backup empty), re-ran:
`1 passed in 0.01s`.

**Test 6 — unreachable node yields `reachable: False`, never zeroed
hardware (Hazard C).** Broke it by changing `_unreachable()` to return
`gpu: [], cpu: {}, ram: {}` instead of `None`. Result, red:

```
tests/test_node_facts.py::TestUnreachableNodeNeverZeroed::test_ssh_failure_yields_null_hardware_not_zeros
> assert result["gpu"] is None
E AssertionError: assert [] is None

tests/test_node_facts.py::TestUnreachableNodeNeverZeroed::test_ssh_nonzero_exit_also_yields_unreachable
> assert result["gpu"] is None
E AssertionError: assert [] is None

2 failed in 0.03s
```

Restored from backup (`diff` empty), re-ran full `test_node_facts.py`:
`15 passed in 0.09s`. Ruff re-checked clean after restore.

## Real run against LUCIFER (verbatim) — the acceptance evidence

```
$ /home/sy5/owui/bin/python3 tools/node_facts.py --all --json
```

```json
{
  "hardware": {
    "node4090": {
      "node": "node4090",
      "gpu": [
        {
          "name": "NVIDIA GeForce RTX 4090",
          "vram_total_mib": 24564,
          "driver": "610.74",
          "cuda": "13.3",
          "vram_bandwidth_gbps": null,
          "bandwidth_source": "not-probed"
        }
      ],
      "cpu": {
        "model": "Intel(R) Core(TM) i9-14900KF",
        "sockets": 1,
        "cores": 10,
        "threads": 20,
        "isa_flags": ["avx", "avx2", "avx_vnni"]
      },
      "ram": {"total_gib": 47.04, "available_gib": 37.68},
      "host": {"hostname": "LUCIFER", "kernel": "6.18.33.2-microsoft-standard-WSL2", "reachable": true},
      "probed_at": "2026-08-02T19:17:50.549242+00:00",
      "source": "local-probe"
    },
    "node3090": {
      "node": "node3090",
      "gpu": [
        {
          "name": "NVIDIA GeForce RTX 3090",
          "vram_total_mib": 24576,
          "driver": "610.43.02",
          "cuda": "13.3",
          "vram_bandwidth_gbps": null,
          "bandwidth_source": "not-probed"
        }
      ],
      "cpu": {
        "model": "Intel(R) Core(TM) i9-9900K CPU @ 3.60GHz",
        "sockets": 1,
        "cores": 8,
        "threads": 16,
        "isa_flags": ["avx", "avx2"]
      },
      "ram": {"total_gib": 31.25, "available_gib": 20.13},
      "host": {"hostname": "node3090", "kernel": "6.8.0-136-generic", "reachable": true},
      "probed_at": "2026-08-02T19:17:50.615667+00:00",
      "source": "ssh"
    },
    "node5090": {
      "node": "node5090",
      "gpu": null, "cpu": null, "ram": null,
      "host": {"hostname": null, "kernel": null, "reachable": false},
      "probed_at": "2026-08-02T19:17:51.187919+00:00",
      "source": "unreachable"
    }
  },
  "models": {
    "probed_at": "2026-08-02T19:17:51.342614+00:00",
    "roots": [
      {"root": "/home/sy5/models", "reachable": true, "source": "local-scan", "files": ["...7 files, see full JSON at /tmp/node-facts-real-run.json..."]},
      {"root": "/opt/local-se/nas/Models", "reachable": true, "source": "local-scan", "files": ["...24 files, see full JSON..."]}
    ]
  },
  "match": {
    "live_pid": 335865,
    "live_model": "/home/sy5/models/DavidAU/Qwen3.6-27B-Fable-Fus-711-UnHeretic-NM-DAU-NEO-MAX-NEO-MTP-Q4_K_M.gguf",
    "best_match": {
      "file": "/mnt/c/Goethe3.0/Qwen3.6-27B-UD-Q4_K_XL-165000.gguf.md",
      "identity_matches": 16,
      "identity_total": 31
    },
    "verdict": "closest"
  }
}
```

Full verbatim output (all 4 ranked profiles with complete diffs, all 31
model files) is saved at `/tmp/node-facts-real-run.json` (797 lines) —
abbreviated above only for report length.

**What this run demonstrates, unprompted:**

- `node5090` really is asleep/unreachable right now, and the tool reported
  exactly that — `reachable: false`, every hardware field `null`, nothing
  guessed. Hazard C, proven at runtime, not just by test.
- `node3090` turned out to be **awake and reachable** during this session
  (ground-truth table said "asleep at time of writing" as of 2026-07-29;
  see correction below).
- A real llama-server is running locally on LUCIFER (pid 335865) serving a
  **different model** (`DavidAU/...Fable-Fus-711...`) than any of the four
  canonical profiles (`unsloth/Qwen3.6-27B-UD-Q4_K_XL.gguf` or
  `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf`). The tool correctly reports
  `verdict: "closest"` rather than a false "exact", and every ranked
  profile's `--host` difference (`0.0.0.0` canonical vs `127.0.0.1` live)
  lands in `deployment_diffs`, never `identity_diffs` — Hazard A holding
  under real, not synthetic, data.
- The live server is also running `--path
  /home/sy5/.local/share/lse/llama-ui/releases/...` (a flag none of the
  four canonical files set) — correctly classified `deployment`, so it
  doesn't inflate the identity-diff count either.

## Ground-truth (spec §2) corrections found during implementation

- **Remote model root**: the spec's table says `//n45.home.arpa/Models`.
  That literal UNC-style path is not directly accessible; the share is
  already mounted system-wide via `cifs`/`autofs` at
  `/opt/local-se/nas/Models` (confirmed via `mount | grep n45`). Used that
  path as the second `collect_models()` root instead.
- **node3090 reachability**: the ground-truth table (compiled 2026-07-29,
  per `goethe_node.py`'s own comment) says node3090 was asleep. During this
  session (2026-08-02) it was awake and reachable — SSH succeeded,
  hardware facts collected normally, `source: "ssh"`. Fleet state changes
  fast, as the spec itself warns.
- **`nvidia-smi` CUDA version format**: on this WSL2 host, `nvidia-smi`'s
  header prints `CUDA UMD Version: 13.3`, not the classic `CUDA Version:
  12.x` line most non-WSL hosts show. `_parse_cuda()` matches both forms
  (`CUDA(?:\s+UMD)?\s+Version:\s*([\d.]+)`).
- Everything else in the table (node4090 = LUCIFER, RTX 4090/24564 MiB,
  i9-14900KF/20 CPU/47 GB RAM, 7 local GGUFs, 4 profile files, 728-test
  baseline) held exactly as documented.

## What was proven at runtime vs. by test only

- **Runtime-proven**: local hardware probe (node4090/LUCIFER), remote SSH
  probe of an actually-awake node (node3090), remote-unreachable path
  against an actually-asleep node (node5090, no synthetic mocking
  involved), local + NAS-share model enumeration, and a live profile match
  against a real running llama-server process.
- **Test-only** (mocked `subprocess.run`, spec explicitly allows this for
  determinism since node3090/node5090 wake state isn't controllable from
  this task): the synthetic SSH-timeout and SSH-nonzero-exit unreachable
  paths (test 6), and the synthetic-flags identity/deployment diff and
  ranking behavior (tests 2, 3, 4) — these don't depend on which real node
  happens to be awake when the suite runs.

## Not done (anti-goals, confirmed out of scope)

No profile generation, tuning, or recommendation; no engine start/stop;
no web fetches, including for VRAM bandwidth; no `_NODE_REGISTRY` or
`goethe_node.py` changes; no node wake; no model file hashing or content
reads.
