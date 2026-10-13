#!/usr/bin/env bash
# Create a video project folder.  Usage: new_project.sh <slug> ["Title"]
set -euo pipefail
SLUG="$1"; TITLE="${2:-$1}"
ROOT="${VIDEO_ROOT:-$HOME/Movies/talking-head-video}"
P="$ROOT/$SLUG"
SKILL="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$P/raw" "$P/screens" "$P/out"
[[ -f "$P/project.json" ]] || cat > "$P/project.json" <<JSON
{
  "slug": "$SLUG",
  "title": "$TITLE",
  "vocab": []
}
JSON
[[ -f "$P/script.md" ]] || sed "s/{{TITLE}}/$TITLE/" "$SKILL/templates/script.md" > "$P/script.md"
echo "$P"
