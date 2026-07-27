#!/usr/bin/env python3
"""Staged, resumable TRAUM A/B learning-lift evaluation registry.

The CLI only freezes local files, records isolated-worker artifacts, and
computes paired statistics.  It performs no network or production writes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traum_eval_registry import (
    EvalError,
    analyze_evaluation,
    capture_condition_b,
    create_evaluation,
    evidence_summary,
    freeze_condition_a,
    get_status,
    list_statuses,
    open_condition_b,
    record_evidence,
    record_trial,
)


DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "eval" / "traum-registry"


def _add_capture_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--eval-id", required=True)
    parser.add_argument("--mapping", required=True, help="isolated mapping export JSON")
    parser.add_argument("--documents", required=True, help="isolated document export JSONL")
    parser.add_argument("--config", required=True, help="retrieval/store configuration JSON")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="file-backed eval registry root")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="freeze an immutable v2 eval plan")
    init.add_argument("--spec", required=True, help="path to a traum.eval.spec.v2 JSON document")

    freeze_a = commands.add_parser("freeze-a", help="freeze Condition A mapping/docs/config")
    _add_capture_args(freeze_a)

    open_b = commands.add_parser("open-b", help="open B only after the real minimum elapsed window")
    open_b.add_argument("--eval-id", required=True)

    capture_b = commands.add_parser("capture-b", help="capture isolated Condition B after open-b")
    _add_capture_args(capture_b)

    trial = commands.add_parser("record-trial", help="record one immutable paired-trial member")
    trial.add_argument("--eval-id", required=True)
    trial.add_argument("--condition", choices=("A", "B"), required=True)
    trial.add_argument("--seed", type=int, required=True)
    trial.add_argument("--metrics", required=True, help="traum.eval.trial.v2 metrics JSON")
    trial.add_argument("--artifact", action="append", required=True, help="raw transcript/retrieval artifact; repeatable")

    analyze = commands.add_parser("analyze", help="compute paired confidence intervals and gates")
    analyze.add_argument("--eval-id", required=True)

    status = commands.add_parser("status", help="stable GUI-facing machine status")
    status.add_argument("--eval-id", help="omit to list every evaluation")

    evidence = commands.add_parser("record-evidence", help="append immutable continuous-learning evidence")
    evidence.add_argument("--event", required=True, help="traum.continuous-evidence.v1 JSON")

    commands.add_parser("evidence-status", help="summarize proposal-type evidence and future eligibility")
    return parser


def _dispatch(args: argparse.Namespace):
    registry = args.registry
    if args.command == "init":
        return create_evaluation(registry, args.spec)
    if args.command == "freeze-a":
        return freeze_condition_a(registry, args.eval_id, args.mapping, args.documents, args.config)
    if args.command == "open-b":
        return open_condition_b(registry, args.eval_id)
    if args.command == "capture-b":
        return capture_condition_b(registry, args.eval_id, args.mapping, args.documents, args.config)
    if args.command == "record-trial":
        return record_trial(registry, args.eval_id, args.condition, args.seed, args.metrics, args.artifact)
    if args.command == "analyze":
        return analyze_evaluation(registry, args.eval_id)
    if args.command == "status":
        return get_status(registry, args.eval_id) if args.eval_id else list_statuses(registry)
    if args.command == "record-evidence":
        return record_evidence(registry, args.event)
    if args.command == "evidence-status":
        return evidence_summary(registry)
    raise AssertionError(args.command)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
    except EvalError as exc:
        error = {
            "schema_version": "traum.eval.error.v2",
            "error": {"code": exc.code, "message": str(exc)},
        }
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 2
    indent = None if args.compact else 2
    print(json.dumps(result, indent=indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
