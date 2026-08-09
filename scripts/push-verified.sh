#!/usr/bin/env bash
# push-verified.sh — push the current branch and PROVE it landed.
#
# Why this exists
# ---------------
# Pushing is about 5% mechanics and 95% verification, and the verification is
# the part that goes wrong. The failure is never "the command errored" — it is
# "the command printed something and a human or a model read success into it".
# Measured on this repo:
#
#   2026-08-08  an LSE implementer reported baseline 781 against an actual 830
#               and read a real failure as pre-existing.
#   2026-08-09  the Opus reviewer ran a push whose ground-truth step printed
#               NOTHING — an empty commit list and a blank count, because the
#               remote branch did not exist yet — and pushed anyway, because
#               the steps were chained with `;` instead of `&&`. A new remote
#               branch appeared that nobody had approved.
#
# Both are the same bug in the operator, not the tool: a gate you do not halt
# on is not a gate. So this script halts. It exits non-zero on anything it
# cannot prove, and the ONLY success path ends with local and remote resolving
# to the identical SHA with zero commits outstanding.
#
# That is what makes the git step delegable. "Read this output and tell me if
# it worked" is a judgement task. "Run this and paste the exit code" is not.
#
# Usage
#   scripts/push-verified.sh              # show what would transfer, then stop
#   scripts/push-verified.sh --push       # actually push, then verify
#
# Exit codes
#   0  pushed (or nothing to push) AND verified: local == remote, 0 remaining
#   1  refused: a precondition failed
#   2  refused: protected branch, or a force was requested
#   3  PUSH SUCCEEDED BUT VERIFICATION FAILED — investigate before retrying
set -uo pipefail

PROTECTED_BRANCHES="master main"
DO_PUSH=0
[ "${1:-}" = "--push" ] && DO_PUSH=1

die()  { echo "[push-verified] REFUSED: $*" >&2; exit 1; }
die2() { echo "[push-verified] REFUSED: $*" >&2; exit 2; }

# ── preconditions ───────────────────────────────────────────────────────────
git rev-parse --git-dir >/dev/null 2>&1 || die "not inside a git repository"

BR=$(git rev-parse --abbrev-ref HEAD) || die "cannot resolve HEAD"
[ "$BR" = "HEAD" ] && die "detached HEAD; check out a branch first"

for p in $PROTECTED_BRANCHES; do
  [ "$BR" = "$p" ] && die2 "'$BR' is protected. Open a topic branch."
done

# A dirty tree means the thing you are pushing is not the thing you tested.
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
  echo "[push-verified] tracked files are modified:" >&2
  git status --short --untracked-files=no >&2
  die "commit or stash first — a dirty tree means the push is not what you tested"
fi

git remote get-url origin >/dev/null 2>&1 || die "no 'origin' remote"

echo "[push-verified] branch: $BR"
git fetch -q origin || die "git fetch failed; cannot establish ground truth"

# ── ground truth ────────────────────────────────────────────────────────────
# NEVER @{u}: a remote branch existing is not the same as tracking being
# configured. Verified 2026-08-08 on this repo — origin/codex/fix-sudo-grants-
# live existed while `git log @{u}..HEAD` died with "no upstream configured",
# which reads exactly like "nothing is pushed".
if git rev-parse --verify -q "origin/$BR" >/dev/null; then
  REMOTE_EXISTS=1
  AHEAD=$(git rev-list --count "origin/$BR..HEAD") || die "cannot count outstanding commits"
  BEHIND=$(git rev-list --count "HEAD..origin/$BR") || die "cannot count remote-only commits"
else
  REMOTE_EXISTS=0
  AHEAD=$(git rev-list --count HEAD)
  BEHIND=0
  echo "[push-verified] NOTE: origin/$BR does not exist — this would CREATE a new remote branch."
fi

# The empty-output trap that bit the reviewer: refuse anything non-numeric.
case "$AHEAD" in ''|*[!0-9]*) die "ground truth is not a number ('$AHEAD') — refusing to guess";; esac

if [ "$BEHIND" -gt 0 ]; then
  die "origin/$BR is $BEHIND commit(s) ahead of you. Integrate first; this script never forces."
fi

if [ "$AHEAD" -eq 0 ]; then
  echo "[push-verified] nothing to push — already up to date at $(git rev-parse --short HEAD)"
  exit 0
fi

echo "[push-verified] $AHEAD commit(s) would transfer to origin/$BR:"
git log --oneline "$( [ "$REMOTE_EXISTS" = 1 ] && echo "origin/$BR..HEAD" || echo HEAD )" | sed 's/^/    /'

if [ "$DO_PUSH" -eq 0 ]; then
  echo "[push-verified] dry run. Re-run with --push to send these."
  exit 0
fi

# ── push ────────────────────────────────────────────────────────────────────
echo "[push-verified] pushing (fast-forward only, never forced)…"
GIT_TERMINAL_PROMPT=0 git push --porcelain origin "HEAD:$BR"
PUSH_RC=$?
[ "$PUSH_RC" -ne 0 ] && die "git push exited $PUSH_RC — nothing verified"

# ── verify: the only thing that counts ──────────────────────────────────────
# "Everything up-to-date" is not "I pushed what was asked".
git fetch -q origin || { echo "[push-verified] FAILED: cannot re-fetch to verify" >&2; exit 3; }

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BR" 2>/dev/null || echo "MISSING")
REMAINING=$(git rev-list --count "origin/$BR..HEAD" 2>/dev/null || echo "?")

echo "[push-verified] local  $LOCAL"
echo "[push-verified] remote $REMOTE"
echo "[push-verified] remaining $REMAINING"

if [ "$LOCAL" != "$REMOTE" ] || [ "$REMAINING" != "0" ]; then
  echo "[push-verified] FAILED: push reported success but the remote does not match." >&2
  echo "[push-verified] Do NOT retry blindly and do NOT force. Report this verbatim." >&2
  exit 3
fi

echo "[push-verified] VERIFIED: $AHEAD commit(s) transferred; local and remote agree."
exit 0
