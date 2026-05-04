#!/usr/bin/env bash
# Start the Avid Transcription local server (macOS / Linux).
# Keep this terminal window open while using Avid.

set -euo pipefail

PORT="${AVID_TRANSCRIPTION_PORT:-8765}"

echo "Starting Avid Transcription server on http://localhost:$PORT"
echo "Keep this window open while working in Avid."
echo "Press Ctrl+C to stop."
echo ""

avid-transcription --server --port "$PORT"
