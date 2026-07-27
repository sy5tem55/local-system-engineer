# TRAUM User Manual

This page is the short entry point for day-to-day TRAUM operation. The
canonical, current guide is the
[TRAUM GUI Operator Manual](TRAUM-OPERATOR-MANUAL.md).

## Routine workflow

1. Open the Goethe Console at `http://localhost:9700/ui` and enter the existing
   `GOETHE_MCP_TOKEN`.
2. Read **TRAUM — Dream Digest**, then inspect the canonical run and attempt
   states.
3. Review only actionable items in **TRAUM — Human Gate**. Preview before any
   decision; acknowledge investigated failures and archive terminal history
   when it no longer belongs in the default view.
4. Treat the A/B panel as monitoring evidence, not as permission to apply or
   promote a policy.

The Console is the routine control surface. CLI commands remain available for
expert recovery, deployment, and isolated evaluation; see
[Operations Runbook §10](07-operations-runbook.md#10-dreaming-operations-traum).

## Control boundary

TRAUM does not change **Permissions — Pending Approvals**, **Active Grants**,
or the sudo delegation/grant workflow. Nightly timer status is read-only in the
Console. Proposal approval remains a separate typed Human Gate decision; there
is no blanket auto-apply switch in the GUI.

## Historical note

The previous version of this page described the CLI-first workflow verified on
2026-07-17. That record remains in Git history and the expert procedures remain
in the operations runbook. The 2026-07-14 v1 evaluation's protocol verdict was
**LOSS** and its causal interpretation was **INCONCLUSIVE**; it did not earn an
auto-apply policy. See the
[historical v1 report](../eval/eval-report-traum-1.md).
