#!/bin/bash
# WhisperBar installer
# Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/austinosborn/whisperbar/main/install.sh)"

set -e

REPO="austinosborn/whisperbar"
APP_NAME="WhisperBar.app"
INSTALL_DIR="/Applications"
TMP_DIR=$(mktemp -d)

echo ""
echo "Installing WhisperBar..."
echo ""

# ── Download latest release ───────────────────────────────────────────────────
LATEST_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep "browser_download_url.*zip" \
  | cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
  echo "Error: Could not find a release to download. Check https://github.com/$REPO/releases"
  exit 1
fi

echo "Downloading $(basename "$LATEST_URL")..."
curl -fsSL "$LATEST_URL" -o "$TMP_DIR/WhisperBar.zip"

# ── Unzip and install ─────────────────────────────────────────────────────────
echo "Installing to $INSTALL_DIR..."
unzip -q "$TMP_DIR/WhisperBar.zip" -d "$TMP_DIR"
rm -rf "$INSTALL_DIR/$APP_NAME"
cp -R "$TMP_DIR/$APP_NAME" "$INSTALL_DIR/$APP_NAME"
rm -rf "$TMP_DIR"

# ── Clear Gatekeeper quarantine ───────────────────────────────────────────────
xattr -cr "$INSTALL_DIR/$APP_NAME"

echo ""
echo "WhisperBar installed."
echo ""
echo "Opening required permissions in System Settings..."
echo "Enable 'Terminal' (or 'WhisperBar') in each pane that opens."
echo ""
sleep 1

# ── Open each permission pane ─────────────────────────────────────────────────
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
sleep 2
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
sleep 2
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"

echo "Once all three permissions are granted, open WhisperBar from your Applications folder."
echo ""
