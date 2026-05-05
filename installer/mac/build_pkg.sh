#!/usr/bin/env bash
# Build AvidTranscription-<version>-macOS.pkg
# Must be run from the repo root:  bash installer/mac/build_pkg.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VERSION="${1:-1.0.0}"
PKG_ID="com.avidtranscription.plugin"
OUTPUT_DIR="$SCRIPT_DIR/Output"

echo "Building macOS installer for version $VERSION …"

# ── Locate the wheel ─────────────────────────────────────────────────────────
WHEEL=$(ls "$REPO_ROOT/dist/avid_transcription-${VERSION}-"*.whl 2>/dev/null | head -1 || true)
if [ -z "$WHEEL" ]; then
  WHEEL=$(ls "$REPO_ROOT/dist/"*.whl 2>/dev/null | head -1 || true)
fi
if [ -z "$WHEEL" ]; then
  echo "ERROR: No wheel found in $REPO_ROOT/dist/. Run 'python -m build' first." >&2
  exit 1
fi
echo "  Wheel: $(basename "$WHEEL")"

# ── Assemble payload ──────────────────────────────────────────────────────────
PAYLOAD="$SCRIPT_DIR/payload"
rm -rf "$PAYLOAD"
mkdir -p "$PAYLOAD/Library/AvidTranscription"

# Bundled relocatable Python (python-build-standalone) with our package
# pre-installed — created by CI before calling this script.
PYTHON_PAYLOAD="$SCRIPT_DIR/python_payload"
if [ -d "$PYTHON_PAYLOAD" ]; then
  echo "  Bundling relocatable Python …"
  cp -r "$PYTHON_PAYLOAD" "$PAYLOAD/Library/AvidTranscription/python"
else
  echo "ERROR: python_payload not found at $PYTHON_PAYLOAD" >&2
  exit 1
fi

# Wheel (kept for reference / manual reinstall)
cp "$WHEEL" "$PAYLOAD/Library/AvidTranscription/"

# Panel files
cp -r "$REPO_ROOT/avid_panel/." "$PAYLOAD/Library/AvidTranscription/avid_panel/"

# App bundle
cp -r "$SCRIPT_DIR/app/AvidTranscription.app" "$PAYLOAD/Library/AvidTranscription/"
chmod +x "$PAYLOAD/Library/AvidTranscription/AvidTranscription.app/Contents/MacOS/AvidTranscription"

# ── Make scripts executable ────────────────────────────────────────────────
chmod +x "$SCRIPT_DIR/scripts/preinstall"
chmod +x "$SCRIPT_DIR/scripts/postinstall"
[ -f "$SCRIPT_DIR/scripts/preuninstall" ] && chmod +x "$SCRIPT_DIR/scripts/preuninstall"

# ── Build component package ──────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
COMPONENT_PKG="$SCRIPT_DIR/avid-transcription-component.pkg"

pkgbuild \
  --root "$PAYLOAD" \
  --scripts "$SCRIPT_DIR/scripts" \
  --identifier "$PKG_ID" \
  --version "$VERSION" \
  --install-location "/" \
  "$COMPONENT_PKG"

# ── Build distribution package ───────────────────────────────────────────────
OUTPUT_PKG="$OUTPUT_DIR/AvidTranscription-${VERSION}-macOS.pkg"

productbuild \
  --distribution "$SCRIPT_DIR/Distribution.xml" \
  --resources "$SCRIPT_DIR" \
  --package-path "$SCRIPT_DIR" \
  "$OUTPUT_PKG"

# ── Cleanup temp files ───────────────────────────────────────────────────────
rm -f "$COMPONENT_PKG"
rm -rf "$PAYLOAD"

echo ""
echo "✔  Built: $OUTPUT_PKG"
echo "   Size:  $(du -sh "$OUTPUT_PKG" | cut -f1)"
