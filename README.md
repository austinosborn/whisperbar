# WhisperBar

A macOS status bar app that transcribes your speech and types it anywhere — hold a hotkey, speak, release, and the text is pasted into whatever is focused.

Built on [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (a fast, CPU-friendly Whisper implementation). No internet connection required after the model downloads on first use.

---

## Requirements

- macOS 12 or later (Apple Silicon or Intel)
- Python 3.9+ (included with macOS)

That's it. Homebrew, sox, and Python dependencies are installed automatically on first launch.

---

## Installation

Paste this into Terminal and press Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/austinosborn/whisperbar/main/install.sh)"
```

This downloads WhisperBar, installs it to your Applications folder, clears the macOS security flag, and opens the three permission panes you'll need to grant access in.

> **Why not just double-click?** macOS blocks unsigned apps downloaded from the internet. The install script handles this automatically. Signing requires an Apple Developer membership — something we may add in a future release.

---

## First Launch

When you open WhisperBar for the first time, it will automatically set up everything it needs:

1. **Homebrew** — if not installed, a Terminal window opens and installs it. Relaunch WhisperBar when it's done.
2. **sox** — if not installed, a Terminal window opens and runs `brew install sox`. Relaunch when done.
3. **Python dependencies** — a Terminal window installs `faster-whisper` and friends into the app's private environment. Relaunch when done.

Each of these only happens once.

---

## macOS Permissions

WhisperBar needs three permissions. It will prompt you for most of them, but here's the full picture:

### Accessibility *(app will prompt you)*

**System Settings → Privacy & Security → Accessibility**

Required so WhisperBar can detect your hotkey. If this isn't granted, WhisperBar will show a dialog with an **Open Settings** button that takes you directly there.

After enabling it, quit and relaunch WhisperBar.

### Input Monitoring *(manual)*

**System Settings → Privacy & Security → Input Monitoring**

Also required for the hotkey listener. Enable **Terminal** in this list.

This one can't be detected automatically — if your hotkey isn't working and Accessibility is already granted, this is likely the missing piece.

### Microphone *(macOS will prompt)*

macOS will ask for microphone access the first time WhisperBar tries to record. Click **Allow**.

---

## Usage

Once running, a 🎙️ icon appears in your menu bar.

| Action | Result |
|---|---|
| **Hold hotkey** (default: Right Control) | Starts recording |
| **Release hotkey** | Stops recording and transcribes |
| **Transcribed text** | Pasted into the currently focused app |

The menu icon updates to show the current state (Idle / 🔴 Recording / ⏳ Transcribing).

### Menu options

| Option | Description |
|---|---|
| **Status** | Current state |
| **Hotkey** | Active hotkey |
| **Set Hotkey…** | Press any key to reassign |
| **Toggle Mode** | Switch between hold-to-record and press-to-start/press-to-stop |
| **Show Terminal** | View live transcription output and logs |

---

## Configuration

### Hotkey

1. Click the 🎙️ menu bar icon
2. Click **Set Hotkey…**
3. Press the key you want to use

Saved automatically to `~/.whisper_dictation.json`.

### Toggle Mode vs Hold Mode

**Hold Mode** (default): hold the hotkey while speaking, release when done.

**Toggle Mode**: press once to start, press again to stop — better for longer dictation or if holding a key is uncomfortable.

Enable it: 🎙️ menu → **Toggle Mode**.

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

The model downloads automatically from Hugging Face on first use.

---

## Troubleshooting

**Hotkey does nothing**
- Check that Terminal has **Accessibility** permission — WhisperBar will prompt you if not.
- Also check **Input Monitoring** (System Settings → Privacy & Security → Input Monitoring). This one requires manual action.
- Quit and relaunch after granting either permission.

**No audio / sox errors in Terminal**
- WhisperBar installs sox automatically, but if something went wrong: `brew install sox`.
- Check that Terminal has **Microphone** permission.

**Transcription is slow**
- The first transcription after launch takes longer while the model loads. It's faster after that.
- Switch to `tiny.en` for faster (but less accurate) results.

**"WhisperBar is already running" and the app closes**
- Only one instance runs at a time. Look for the 🎙️ icon in your menu bar.
- If the icon is missing but the app won't launch: `rm /tmp/whisper_dictation.lock`

**Text isn't pasting**
- The app injects Cmd+V via CoreGraphics. Most apps support this.
- Some apps (games, certain terminals) may block synthetic keyboard input.

---

## How it works

1. `pynput` listens for the configured hotkey system-wide.
2. On press, `sox` records from the default microphone to a temp WAV file.
3. On release, `faster-whisper` transcribes the audio locally on CPU.
4. The text is copied to the clipboard, pasted with a synthetic Cmd+V (CoreGraphics), and the previous clipboard contents are restored.

---

## License

MIT
