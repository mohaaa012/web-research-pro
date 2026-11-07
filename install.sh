#!/usr/bin/env bash
# Web Research Pro — installer for macOS and Linux.
#
#   curl -fsSL https://raw.githubusercontent.com/mohaaa012/web-research-pro/main/install.sh | bash
#
# Options (when piping, pass them after "bash -s --", e.g. ... | bash -s -- --no-browser):
#   --project      install into ./.claude/skills (this project only) instead of ~/.claude/skills
#   --dir PATH     install into PATH/web-research-pro
#   --no-browser   skip the Chromium download (no JavaScript pages, screenshots or login windows)
#   --uninstall    remove the skill (your data in ~/.web-research-pro is kept)
set -euo pipefail

REPO="mohaaa012/web-research-pro"
BRANCH="${WRP_BRANCH:-main}"
SKILL="web-research-pro"
DEST_BASE="${HOME}/.claude/skills"
NO_BROWSER=0
UNINSTALL=0

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!! \033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31mxx \033[0m %s\n' "$*" >&2; exit 1; }

usage() { sed -n '2,11p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//' || true; }

while [ $# -gt 0 ]; do
  case "$1" in
    --project) DEST_BASE="$(pwd)/.claude/skills" ;;
    --dir) shift; [ $# -gt 0 ] || die "--dir needs a path"; DEST_BASE="$1" ;;
    --no-browser) NO_BROWSER=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (use --help)" ;;
  esac
  shift
done
DEST="${DEST_BASE%/}/${SKILL}"

is_our_skill() { [ -f "$1/SKILL.md" ] && grep -q "^name: ${SKILL}\$" "$1/SKILL.md"; }

if [ "$UNINSTALL" = 1 ]; then
  if is_our_skill "$DEST"; then
    rm -rf "$DEST"
    say "removed ${DEST}"
  else
    warn "web-research-pro is not installed in ${DEST}"
  fi
  if [ -d "${HOME}/.web-research-pro" ]; then
    say "kept ~/.web-research-pro (private venv, saved logins, monitors). To delete it too: rm -rf ~/.web-research-pro"
  fi
  exit 0
fi

# 1. Python 3.9+
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  die "Python 3.9 or newer is required.
    macOS:          brew install python   (or https://www.python.org/downloads/)
    Ubuntu/Debian:  sudo apt install python3 python3-venv
    Fedora:         sudo dnf install python3"
fi
say "using $("$PY" --version 2>&1) ($(command -v "$PY"))"

# 2. Get the files: this checkout if we run from one, otherwise download.
SRC=""
SCRIPT_DIR=""
if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi
if [ -n "$SCRIPT_DIR" ] && is_our_skill "${SCRIPT_DIR}/skills/${SKILL}"; then
  SRC="${SCRIPT_DIR}/skills/${SKILL}"
  say "installing from this folder: ${SCRIPT_DIR}"
else
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  say "downloading ${REPO} (${BRANCH}) ..."
  if command -v git >/dev/null 2>&1; then
    git clone --quiet --depth 1 --branch "$BRANCH" "https://github.com/${REPO}.git" "${TMP}/repo" \
      || die "could not download the repository with git"
  elif command -v curl >/dev/null 2>&1; then
    mkdir -p "${TMP}/repo"
    curl -fsSL "https://codeload.github.com/${REPO}/tar.gz/refs/heads/${BRANCH}" \
      | tar -xz -C "${TMP}/repo" --strip-components=1 || die "could not download the repository with curl"
  else
    die "git or curl is required to download the skill"
  fi
  SRC="${TMP}/repo/skills/${SKILL}"
  is_our_skill "$SRC" || die "the download does not contain skills/${SKILL}"
fi

# 3. Copy the skill (replacing an older version of itself only).
mkdir -p "$DEST_BASE"
if [ -e "$DEST" ]; then
  if is_our_skill "$DEST"; then
    say "updating the existing installation"
    rm -rf "$DEST"
  else
    die "${DEST} already exists and is not web-research-pro. Move it away and run again."
  fi
fi
cp -R "$SRC" "$DEST"
rm -rf "${DEST}/evals" "${DEST}/scripts/__pycache__" "${DEST}/scripts/wrp/__pycache__"
say "skill copied to ${DEST}"

# 4. Optional pieces: private venv with Playwright, trafilatura, pypdf + Chromium.
SETUP_ARGS=(--setup)
[ "$NO_BROWSER" = 1 ] && SETUP_ARGS+=(--no-browser)
if ! "$PY" "${DEST}/scripts/doctor.py" "${SETUP_ARGS[@]}"; then
  warn "setup reported a problem (details above). The skill still works with fewer features."
  warn "retry any time with:  $PY ${DEST}/scripts/doctor.py --setup"
fi

cat <<EOF

$(printf '\033[1;32m')✔ Web Research Pro is installed.$(printf '\033[0m')

  Skill:   ${DEST}
  Data:    ~/.web-research-pro  (private venv, saved logins, monitors)

Next steps:
  1. Restart Claude Code (or run /reload-plugins) so it picks up the new skill.
  2. Ask things like:
       "Investiga los juegos de Roblox con más jugadores ahora mismo"
       "Lee este PDF y resúmelo: https://.../paper.pdf"
       "Vigila el precio de https://... y avísame si baja"
  3. Check everything with:  $PY ${DEST}/scripts/doctor.py

Uninstall:  curl -fsSL https://raw.githubusercontent.com/${REPO}/main/install.sh | bash -s -- --uninstall
EOF
