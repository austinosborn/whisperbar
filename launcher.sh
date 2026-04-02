#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

RESOURCES="$(cd "$(dirname "$0")/../Resources" && pwd)"
PYTHON="$RESOURCES/venv/bin/python3"
SCRIPT="$RESOURCES/whisper_statusbar.py"
LOG="$HOME/Library/Logs/WhisperBar.log"

# Check sox
if ! command -v sox &>/dev/null; then
    osascript -e 'display dialog "WhisperBar requires sox.\n\nInstall it with:\n\n    brew install sox\n\n(Get Homebrew at brew.sh)" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Validate venv; rebuild if broken (e.g. after macOS upgrade)
if ! "$PYTHON" -c "import rumps, faster_whisper, pynput, pyperclip" &>/dev/null 2>&1; then
    osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "echo 'Setting up WhisperBar (one-time)...' && python3 -m venv --clear '$RESOURCES/venv' && '$RESOURCES/venv/bin/pip' install faster-whisper pyperclip pynput rumps && echo '=== Done! Relaunch WhisperBar from Applications. ==='"
end tell
APPLESCRIPT
    exit 0
fi

# Run Python as a background child — no Terminal window, no extra dock icon.
# The shell stays alive holding the bundle identity while Python runs quietly.
"$PYTHON" "$SCRIPT" >> "$LOG" 2>&1 &
wait $!
