#!/usr/bin/env bash
# Screenshot a public web page at 2x for use as a screen overlay.
# Usage: capture.sh <url> <out.png> [width=1440] [height=900]
# Pages behind a login won't work headless — take those by hand (see RECORDING.md).
set -euo pipefail
URL="$1"; OUT="$2"; WIDTH="${3:-1440}"; HEIGHT="${4:-900}"
CHROME=$(ls -d ~/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell 2>/dev/null | tail -1 || true)
[[ -x "${CHROME:-}" ]] || CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[[ -x "$CHROME" ]] || { echo "No Chrome found (run: npx hyperframes doctor)"; exit 1; }
mkdir -p "$(dirname "$OUT")"; rm -f "$OUT"
PROFILE=$(mktemp -d)
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --user-data-dir="$PROFILE" --window-size="${WIDTH},${HEIGHT}" --virtual-time-budget=6000 \
  --screenshot="$OUT" "$URL" >/dev/null 2>&1 &
PID=$!
# full Chrome sometimes lingers after writing the file — stop it once the PNG is done
for _ in $(seq 1 90); do
  if ! kill -0 $PID 2>/dev/null; then break; fi
  if [[ -s "$OUT" ]]; then sleep 1; kill $PID 2>/dev/null || true; break; fi
  sleep 0.5
done
kill $PID 2>/dev/null || true
rm -rf "$PROFILE"
[[ -s "$OUT" ]] || { echo "capture failed: $URL"; exit 1; }
sips -g pixelWidth -g pixelHeight "$OUT" | tail -2
