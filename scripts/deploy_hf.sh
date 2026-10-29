#!/usr/bin/env bash
# Pushes BEC Guard to a Hugging Face Space (Docker SDK).
#   scripts/deploy_hf.sh https://huggingface.co/spaces/<user>/<space>            # push
#   scripts/deploy_hf.sh https://huggingface.co/spaces/<user>/<space> --dry-run  # list files, push nothing
# Copies only what the container needs (git-tracked or new, never ignored files such as .env) into a temporary
# folder with a Space README (Hugging Face reads its settings from the README header), then force-pushes it.
# Git asks for your Hugging Face username and an access token with write permission as the password.
set -euo pipefail

SPACE_URL="${1:?usage: scripts/deploy_hf.sh <space git url> [--dry-run]}"
ROOT="$(git rev-parse --show-toplevel)"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

cd "$ROOT"
git ls-files --cached --others --exclude-standard -- \
  Dockerfile .dockerignore requirements.txt LICENSE app data scenarios fixtures frontend |
  while read -r f; do [ -f "$f" ] && mkdir -p "$OUT/$(dirname "$f")" && cp "$f" "$OUT/$f"; done

cat > "$OUT/README.md" <<'EOF'
---
title: BEC Guard
emoji: 🛡️
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
license: mit
short_description: Checks payment requests in email before you pay
---

# BEC Guard

Checks payment requests in email before you pay. This Space runs the website and the API; the Gmail add-on, the
source code and the full README are in the GitHub repository.
EOF

if [ -n "$(git status --porcelain)" ]; then
  echo "Note: deploying the working tree, which has uncommitted changes."
fi

if [ "${2:-}" = "--dry-run" ]; then
  (cd "$OUT" && find . -type f | sort)
  echo "Dry run: nothing pushed ($(cd "$OUT" && find . -type f | wc -l | tr -d ' ') files)."
  exit 0
fi

cd "$OUT"
git init -q -b main
git add -A
git commit -qm "Deploy $(git -C "$ROOT" rev-parse --short HEAD)"
git push --force "$SPACE_URL" main
