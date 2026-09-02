# Unsloth Studio leaves an unreaped bash child (zombie) at startup

- Observed: 2026-08-31 15:57 CEST, node4090.
- Signature: exactly one system-wide zombie — `bash`, state `Z+`, owned by sy5,
  parent = the Unsloth Studio python process (`unsloth studio -p 8888`),
  created ~1 s after Studio's own start (Studio 15:53:10, zombie 15:53:11).
- Root cause: Studio spawns a bash subprocess at startup (startup probe), the
  child exits, but Studio never calls waitpid() on it. /proc/<studio>/status
  SigCgt has NO SIGCHLD bit and SigIgn has no SIGCHLD bit either, so the
  default (no-op) action applies and CPython's subprocess auto-reap handler is
  not in effect. The Popen/fork reference is held without wait().
- Impact: zero. VSZ/RSS = 0, no FDs, no CPU. Cost is a single process-table
  slot. It does not accumulate (one per Studio start, reaped when Studio exits
  via reparent-to-init).
- Do NOT kill the parent: it hosts the active inference session (its child is
  the running llama-server). SIGCHLD nudge is useless here (no handler).
- Detection: `ps -eo pid,ppid,stat,comm | awk '$3 ~ /Z/'` — note ps aux STAT is
  field 8, ps -eo with these columns is field 3.
- Fix path: only a Studio restart reaps it early (accepts session interruption);
  otherwise it clears itself on Studio exit. Upstream: report to Unsloth as a
  subprocess-without-wait leak.

Verified against: ps -eo, /proc/9480/status, /proc/9450/status (SigCgt/SigIgn), 2026-08-31.
