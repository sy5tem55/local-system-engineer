#!/usr/bin/env bash
# build-llama-ui.sh — reproducible llama.cpp WebUI builds, pinned by git ref.
#
# WHY THIS EXISTS
#   llama.cpp ships ~10 builds/day and the SvelteKit WebUI rides along with no
#   independent versioning. "Latest" is therefore a moving target that can
#   regress MCP/agentic behaviour without any signal in a release note. This
#   script makes a build a pinned, hash-verified artifact instead: same ref +
#   same toolchain => byte-identical dist, provable via SHA256SUMS.
#
# USAGE
#   build-llama-ui.sh <git-ref> [--name <label>] [--verify <release-dir>]
#     <git-ref>          upstream commit/tag/branch to build (e.g. 17a05e451, b9992)
#     --name <label>     release dir name (default: <ref>-<short-sha>)
#     --verify <dir>     after building, diff SHA256SUMS against an existing
#                        release; non-zero exit if they differ
#
# Refuses to overwrite an existing release. Installed dist is made read-only.
set -euo pipefail

NODE_HOME="${LLAMA_UI_NODE:-$HOME/.nvm/versions/node/v24.16.0}"
SRC="${LLAMA_UI_SRC:-$HOME/lse-builds/llama-ui-src}"
RELEASES="${LLAMA_UI_RELEASES:-$HOME/.local/share/lse/llama-ui/releases}"
UPSTREAM="https://github.com/ggml-org/llama.cpp.git"

REF=""; NAME=""; VERIFY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name)   NAME="$2"; shift 2 ;;
    --verify) VERIFY="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *)        REF="$1"; shift ;;
  esac
done
[ -n "$REF" ] || { echo "error: no git ref given (see --help)" >&2; exit 2; }

[ -x "$NODE_HOME/bin/node" ] || {
  echo "error: node not found at $NODE_HOME/bin/node" >&2
  echo "  the reference build used v24.16.0; system node is $(node -v 2>/dev/null || echo none)." >&2
  echo "  a different major WILL change the dist hashes. set LLAMA_UI_NODE to override." >&2
  exit 3; }
export PATH="$NODE_HOME/bin:$PATH"
echo "[build] node $(node -v)  npm $(npm -v)"

if [ ! -d "$SRC/.git" ]; then
  echo "[build] cloning upstream into $SRC (first run, this is the slow one)"
  git clone --filter=blob:none "$UPSTREAM" "$SRC"
fi
cd "$SRC"
git fetch --quiet origin "$REF" 2>/dev/null || git fetch --quiet origin
git checkout --quiet --detach "$REF"
git clean -qfdx tools/ui
SHA="$(git rev-parse HEAD)"
UI_TREE="$(git rev-parse HEAD:tools/ui)"
: "${NAME:=${REF}-$(git rev-parse --short HEAD)}"
DEST="$RELEASES/$NAME"
[ -e "$DEST" ] && { echo "error: $DEST already exists — releases are immutable, pick another --name" >&2; exit 4; }

echo "[build] ref=$REF sha=${SHA:0:12} ui_tree=${UI_TREE:0:12}"
cd "$SRC/tools/ui"
EV="$(mktemp -d)"
npm ci                       > "$EV/npm-ci.log" 2>&1 || { tail -20 "$EV/npm-ci.log"; exit 5; }
npm run lint  --if-present   > "$EV/lint.log"   2>&1 || echo "[build] WARN lint failed (see evidence)"
npm run test:unit --if-present -- --run > "$EV/test-unit.log" 2>&1 || echo "[build] WARN unit tests failed (see evidence)"
# Determinism: SvelteKit defaults kit.version.name to Date.now(), which lands
# in the bundle as both the version string AND the derived __sveltekit_<hash>
# global. Measured 2026-07-21: that is the ONLY source of variance between two
# builds of the same ref (37 bytes of 8.2MB; zero application-code difference).
# Pinning it to the commit sha makes the dist bit-identical and reproducible.
if [ "${LLAMA_UI_PIN_VERSION:-1}" = "1" ] && ! grep -q "version:" svelte.config.js; then
  echo "[build] pinning kit.version.name=$SHA for a deterministic dist"
  cp svelte.config.js "$EV/svelte.config.js.orig"
  python3 - "$SHA" <<'PY'
import re, sys
sha = sys.argv[1]
src = open("svelte.config.js").read()
src, n = re.subn(r"(kit:\s*\{)", r"\1\n\t\tversion: { name: '%s' }," % sha, src, count=1)
open("svelte.config.js", "w").write(src)
print("  (patched)" if n else "  (WARN: no kit:{} block found, left unpinned)")
PY
fi
npm run build                > "$EV/build.log"  2>&1 || { tail -30 "$EV/build.log"; exit 6; }
[ -f "$EV/svelte.config.js.orig" ] && cp "$EV/svelte.config.js.orig" svelte.config.js
[ -d dist ] || { echo "error: no dist/ produced" >&2; exit 7; }

mkdir -p "$DEST"
cp -r dist "$DEST/dist"
( cd "$DEST/dist" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$DEST/SHA256SUMS"
cat > "$DEST/RELEASE-METADATA.txt" <<META
ref=$REF
sha=$SHA
ui_tree=$UI_TREE
node=$(node -v)
npm=$(npm -v)
built_at=$(date -Is)
META
mkdir -p "$DEST/evidence" && cp "$EV"/*.log "$DEST/evidence/" 2>/dev/null || true
chmod -R a-w "$DEST/dist"
echo "[build] installed -> $DEST  ($(find "$DEST/dist" -type f | wc -l) files)"

if [ -n "$VERIFY" ]; then
  echo "[verify] comparing against $VERIFY"
  if diff <(awk '{print $1, $2}' "$VERIFY/SHA256SUMS" | sort -k2) \
          <(awk '{print $1, $2}' "$DEST/SHA256SUMS"   | sort -k2) > "$EV/verify.diff"; then
    echo "[verify] IDENTICAL — build is reproducible"
  else
    echo "[verify] DIFFERS:"; head -20 "$EV/verify.diff"; exit 8
  fi
fi
echo "[build] run with: llama-server --path $DEST/dist"
