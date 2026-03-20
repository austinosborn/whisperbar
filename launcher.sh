#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

RESOURCES="$(cd "$(dirname "$0")" && pwd)/../Resources"
PYTHON="$RESOURCES/venv/bin/python3"
SCRIPT="$RESOURCES/whisper_statusbar.py"

# Check sox
if ! command -v sox &>/dev/null; then
    osascript -e 'display dialog "Whisper Dictation requires sox.\n\nInstall it with:\n\n    brew install sox\n\n(Get Homebrew at brew.sh)" buttons {"OK"} default button "OK" with icon caution'
    exit 1
fi

# Validate venv; rebuild automatically on a new machine
if ! "$PYTHON" -c "import rumps, faster_whisper, pynput, pyperclip" &>/dev/null 2>&1; then
    osascript <<APPLESCRIPT
tell application "Terminal"
    activate
    do script "echo 'Setting up Whisper Dictation (one-time)...' && python3 -m venv --clear '$RESOURCES/venv' && '$RESOURCES/venv/bin/pip' install faster-whisper pyperclip pynput rumps && echo '=== Done! Relaunch Whisper Dictation from Applications. ==='"
end tell
APPLESCRIPT
    exit 0
fi

osascript <<EOF
tell application "Terminal"
    activate
    set t to do script "\"$PYTHON\" \"$SCRIPT\""
    delay 0.5
    set w to window of t
    set miniaturized of w to true
    do shell script "echo " & (id of w) & " > /tmp/whisper_terminal_wid"
end tell
EOF
