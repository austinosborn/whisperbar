# WhisperBar

A macOS status bar app that transcribes your speech and types it anywhere — press a hotkey, speak, press again, and the text is pasted into whatever is focused.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (a fast, CPU-friendly Whisper implementation). No internet connection required after the model downloads on first use.

---

## Requirements

- macOS 12 or later (Apple Silicon or Intel)
- Python 3.9+ (included with macOS)

Homebrew and sox are installed automatically by the installer if missing.

---

## Installation

Paste this into Terminal and press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/austinosborn/whisperbar/main/install.sh)"
```

The installer will:
1. Install Homebrew and sox if not already present
2. Download and install WhisperBar to `/Applications`
3. Clear the macOS security quarantine flag
4. Open all three required permission panes in System Settings
5. Launch WhisperBar

> **Why not just double-click?** macOS blocks unsigned apps downloaded from the internet. The install script handles this automatically with `xattr -cr`. Signing requires an Apple Developer membership — something we may add in a future release.

---

## Permissions

Three permissions are required. The installer opens each pane automatically — just enable the toggle for **python3** in each one.

| Permission | Purpose |
|---|---|
| **Microphone** | Record your voice |
| **Accessibility** | Paste transcribed text via Cmd+V |
| **Input Monitoring** | Detect your hotkey |

> **Note:** Three System Settings windows will open in the background. Click back through each one and make sure all three are enabled before using WhisperBar.

After granting permissions, WhisperBar is ready to use. On first launch it downloads the Whisper model (~150 MB) — this only happens once.

---

## Usage

WhisperBar runs silently in the background with a 🎙️ icon in your menu bar. A control window opens automatically on launch.

### Default: Toggle Mode

| Action | Result |
|---|---|
| **Press hotkey** (default: Right Command) | Start recording |
| **Press hotkey again** | Stop recording and transcribe |
| **Transcribed text** | Pasted into the currently focused app |

### Hold Mode

Hold the hotkey while speaking, release to transcribe — useful for short bursts.

Switch between modes using the **Hold to Record / Toggle Record** radio buttons in the control window, or via the menu bar icon.

---

## Control Window

The control window opens on every launch and can be reopened from the menu bar icon → **Show Control Window**.

| Control | Description |
|---|---|
| **Click to Record** | Start/stop recording (mirrors the hotkey) |
| **Hotkey** button | Click, then press any key to reassign |
| **Hold / Toggle** radios | Switch recording mode |
| **Log panel** | Live output — shows Python path, model status, transcriptions, and permission warnings |
| **Hide Control Window** | Dismiss the window (app keeps running) |
| **Quit Application** | Stop WhisperBar entirely |

---

## Configuration

### Hotkey

1. Click the 🎙️ menu bar icon → **Set Hotkey…**, or click the Hotkey button in the control window
2. Press the key you want to use

Saved automatically to `~/.whisper_dictation.json`.

### Recording Mode

**Toggle Mode** (default): press once to start, press again to stop. Better for longer dictation or if holding a key is uncomfortable.

**Hold Mode**: hold the hotkey while speaking, release when done.

### Whisper model

Default is `base.en` — English-only, ~150 MB, fast on CPU.

To change it, open `whisper_statusbar.py` inside the app bundle (`Right-click WhisperBar.app → Show Package Contents → Contents/Resources`) and edit the `MODEL_SIZE` line:

```python
MODEL_SIZE = "base.en"   # change this
```

| Model | Size | Notes |
|---|---|---|
| `tiny.en` | ~75 MB | Fastest, least accurate |
| `base.en` | ~150 MB | Default — good balance |
| `small.en` | ~480 MB | More accurate |
| `medium.en` | ~1.5 GB | High accuracy |
| `base` / `small` / `medium` | varies | Multilingual |

---

## Logs

WhisperBar logs to `~/Library/Logs/WhisperBar.log`. The control window's log panel shows live output including:
- The Python path (useful if you need to identify which binary to enable in System Settings)
- Model loading status
- Each transcription result
- Any permission warnings

Open the full log file: menu bar icon → **View Log**.

---

## Troubleshooting

**Hotkey does nothing**
- Check that python3 has **Input Monitoring** permission (System Settings → Privacy & Security → Input Monitoring).
- Also verify **Accessibility** is enabled for python3.
- Quit and relaunch after granting either permission.

**Text isn't pasting**
- python3 needs **Accessibility** permission (System Settings → Privacy & Security → Accessibility). Enable the toggle next to python3.
- Check the control window log panel for a warning — it will tell you if Accessibility isn't granted.

**No audio / nothing transcribed**
- Check that python3 has **Microphone** permission.
- Verify sox is installed: `brew install sox`

**Transcription is slow**
- The first transcription after launch is slower while the model initializes. It's faster after that.
- Switch to `tiny.en` for faster (but less accurate) results.

**"WhisperBar is already running" and the app won't launch**
- Only one instance runs at a time. Look for the 🎙️ icon in your menu bar.
- If the icon is missing: `rm /tmp/whisper_dictation.lock` then relaunch.

**Menu bar icon not visible**
- macOS can hide menu bar icons when the bar is full. Hold Option and drag the 🎙️ icon to reposition it, or open the control window via Spotlight → WhisperBar.

---

## How it works

1. `pynput` listens for the configured hotkey system-wide.
2. On activation, `sox` records from the default microphone to a temp WAV file.
3. On stop, `faster-whisper` transcribes the audio locally on CPU.
4. The text is copied to the clipboard, pasted with a synthetic Cmd+V (CoreGraphics), and the previous clipboard contents are restored.

WhisperBar runs as a background process — no Terminal window, no Dock icon. The shell that launches it holds the app bundle identity while Python runs silently as a child process.

---

## License

MIT
