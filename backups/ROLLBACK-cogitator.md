# Rollback — LSE Cogitator

## Versions
- **DEPLOYED / rollback target** (live in OWUI since P28): **v1.7.19**
  - black-norm `e76d28b611af670d5acbffc02431d06f66a00e33d9e1eaffd12f164eb61364cb`
  - raw       `7c1de10ee36fd518b146ee38bf8241017db9570ccc9161873a84d9cb297cc2bf`
- **BUILT, awaiting scratch-slot test** (P29): **v1.7.20**
  - black-norm `75ad4a6a1227764292b83fa490996a4a95d93dab7c56b8c67a857298048dc6e3`
  - raw       `b5dcfb95d1af4532d3cf21219f03efbab8b85b9d8775695f19bb0833a71d91ca`
  - Sole change vs 1.7.19: `sudo_delegation_block` is now `async` and force-surfaces its
    block to the UI via `__event_emitter__` (type:"message"). Args/return/STOP PROTOCOL
    unchanged. Backward compatible (emitter defaults to None).

## Backups of the rollback target
- `backups/cogitator-v1.7.19-DEPLOYED-20260614.py` — byte-identical to `tools/cogitator-v1.7.19.py`; black-norm verified == `e76d28b6…`.
- Also in git: commit `44e8d31` contains `tools/cogitator-v1.7.19.py`.

## Revert procedure (if v1.7.20 misbehaves in OWUI)
1. OWUI → Admin → Tools → LSE Cogitator → replace the whole body with the contents of
   `backups/cogitator-v1.7.19-DEPLOYED-20260614.py` (or `tools/cogitator-v1.7.19.py`) → Save.
2. Confirm deploy identity (OWUI black-formats on save):
   `python3 -c "import black,hashlib;print(hashlib.sha256(black.format_str(open('tools/cogitator-v1.7.19.py').read(),mode=black.Mode()).encode()).hexdigest())"`
   → expect `e76d28b611af670d5acbffc02431d06f66a00e33d9e1eaffd12f164eb61364cb`.
3. Valve UI overrides are wiped on redeploy — re-set any custom valves from source defaults.

## Roll back if you see
- coroutine / "not awaited" errors → this OWUI build does not await async tool methods (the v1.7.20 async risk).
- `sudo_delegation_block` returns nothing, errors, or double-posts the block.
- any regression in normal (non-sudo) tool calls.
