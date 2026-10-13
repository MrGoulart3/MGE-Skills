#!/usr/bin/env bash
# Link MGE skills into ~/.claude/skills (Claude Code). Usage: ./install.sh [skill ...]  (default: all)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$dest"
names=("$@")
if [ ${#names[@]} -eq 0 ]; then
  for d in "$here"/*/; do [ -f "$d/SKILL.md" ] && names+=("$(basename "$d")"); done
fi
for n in "${names[@]}"; do
  [ -f "$here/$n/SKILL.md" ] || { echo "skip: $n (no SKILL.md)"; continue; }
  ln -sfn "$here/$n" "$dest/$n" && echo "linked $n -> $dest/$n"
done
