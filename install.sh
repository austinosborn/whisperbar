#!/bin/bash
# WhisperBar installer
# Usage: /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/austinosborn/whisperbar/main/install.sh)"

REPO="austinosborn/whisperbar"
APP_NAME="WhisperBar.app"
INSTALL_DIR="/Applications"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  WhisperBar Installer"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Homebrew ──────────────────────────────────────────────────────────────────
if ! command -v brew &>/dev/null; then
  # Try to load it from the standard locations first (common on Apple Silicon)
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
  eval "$(/usr/local/bin/brew shellenv)" 2>/dev/null || true
fi

if ! command -v brew &>/dev/null; then
  echo "→ Installing Homebrew (required for sox)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)" 2>/dev/null || true
  eval "$(/usr/local/bin/brew shellenv)" 2>/dev/null || true
fi

# ── sox ───────────────────────────────────────────────────────────────────────
if ! command -v sox &>/dev/null; then
  echo "→ Installing sox..."
  brew install sox
else
  echo "✓ sox already installed"
fi

# ── Download ──────────────────────────────────────────────────────────────────
echo "→ Fetching latest release..."
TMP_DIR=$(mktemp -d)

LATEST_URL=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest" \
  | grep "browser_download_url.*zip" \
  | cut -d '"' -f 4)

if [ -z "$LATEST_URL" ]; then
  echo ""
  echo "Error: Could not find a release to download."
  echo "Check https://github.com/$REPO/releases"
  rm -rf "$TMP_DIR"
  exit 1
fi

echo "→ Downloading $(basename "$LATEST_URL")..."
curl -fL --progress-bar "$LATEST_URL" -o "$TMP_DIR/WhisperBar.zip"

# ── Install ───────────────────────────────────────────────────────────────────
echo "→ Installing to $INSTALL_DIR..."
unzip -q "$TMP_DIR/WhisperBar.zip" -d "$TMP_DIR"

if [ ! -d "$TMP_DIR/$APP_NAME" ]; then
  echo "Error: $APP_NAME not found in zip. Download may be corrupted."
  rm -rf "$TMP_DIR"
  exit 1
fi

rm -rf "$INSTALL_DIR/$APP_NAME"
cp -R "$TMP_DIR/$APP_NAME" "$INSTALL_DIR/$APP_NAME"
rm -rf "$TMP_DIR"

# ── Clear Gatekeeper quarantine ───────────────────────────────────────────────
xattr -cr "$INSTALL_DIR/$APP_NAME"

echo ""
echo "✓ WhisperBar installed to $INSTALL_DIR/$APP_NAME"
echo ""

# ── Permissions guide ─────────────────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Permissions (3 required)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "System Settings will open for each permission."
echo ""
echo "  1. Microphone       — to record your voice"
echo "  2. Accessibility    — to paste transcribed text"
echo "  3. Input Monitoring — to detect your hotkey"
echo ""
echo "  Enable the toggle for python3 in each pane that opens."
echo ""
echo "Opening System Settings now..."
echo ""
sleep 1

open "x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone"
sleep 1
open "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
sleep 1
open "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"

echo "  ⚠️  Three System Settings windows have opened in the background."
echo "  Click back through each one and make sure all three permissions"
echo "  are enabled before launching WhisperBar."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Launching WhisperBar..."
echo ""
echo "On first launch the Whisper model (~150 MB) will be downloaded."
echo "Once ready, hold Right Command and speak — text pastes on release."
echo ""

open "$INSTALL_DIR/$APP_NAME"

osascript <<'APPLESCRIPT'
display dialog "WhisperBar is installed and running.

Check the control window for permission warnings, then hold Right Command and speak." buttons {"Done"} default button "Done" with icon note
APPLESCRIPT

# Keep the terminal open so the instructions above remain readable.
exec $SHELL
