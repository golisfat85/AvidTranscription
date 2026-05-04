#!/usr/bin/env bash
# Install the Avid Transcription panel into Avid Media Composer (macOS / Linux).
# Run once after installing the Python package.

set -euo pipefail

PANEL_NAME="AvidTranscription"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PANEL_SRC="$(cd "$SCRIPT_DIR/../avid_panel" && pwd)"

# Avid panel directory (macOS)
AVID_PANELS_DIR="$HOME/Library/Application Support/Avid/Avid Media Composer/SupportingFiles/Panels"

# Fallback for Linux (uncommon but possible)
if [[ "$(uname)" != "Darwin" ]]; then
  AVID_PANELS_DIR="$HOME/.avid/Avid Media Composer/SupportingFiles/Panels"
fi

DEST="$AVID_PANELS_DIR/$PANEL_NAME"

echo "Installing Avid Transcription panel..."
echo "  Source : $PANEL_SRC"
echo "  Destination : $DEST"

mkdir -p "$DEST"
cp -r "$PANEL_SRC/." "$DEST/"

echo ""
echo "Panel installed successfully."
echo ""
echo "Next steps:"
echo "  1. Start the transcription server:"
echo "       avid-transcription --server"
echo "     or run the start script:"
echo "       bash \"$(dirname "$0")/start_server.sh\""
echo ""
echo "  2. Open Avid Media Composer."
echo "  3. Go to  Windows → Panels → AvidTranscription"
echo "     (You may need to restart Media Composer once after first install.)"
