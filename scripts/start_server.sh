#!/usr/bin/env bash
# Start the Avid Transcription local server (macOS / Linux).
# Uses 'python -m avid_transcription.main' so it works even if the
# avid-transcription script is not on PATH.

PORT="${AVID_TRANSCRIPTION_PORT:-8765}"

# Find Python
SEARCH_PATHS=(
  /usr/local/bin/python3
  /opt/homebrew/bin/python3
  /usr/bin/python3
  python3
  python
)

PYTHON=""
for p in "${SEARCH_PATHS[@]}"; do
  if command -v "$p" &>/dev/null || [ -x "$p" ]; then
    VER=$("$p" -c "import sys; print(sys.version_info >= (3,9))" 2>/dev/null || echo "False")
    if [ "$VER" = "True" ]; then
      PYTHON="$p"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.9+ not found. Install from https://www.python.org/downloads/"
  exit 1
fi

echo "======================================"
echo "  Avid Transcription Server"
echo "======================================"
echo ""
echo "  Panel URL : http://localhost:$PORT"
echo "  Python    : $PYTHON"
echo ""
echo "  Open http://localhost:$PORT in your"
echo "  browser while working in Avid."
echo ""
echo "  Press Ctrl+C to stop."
echo ""

"$PYTHON" -m avid_transcription.main --server --port "$PORT"
