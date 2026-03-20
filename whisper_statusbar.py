#!/usr/bin/env python3
"""
WhisperBar — macOS status bar app
Hold hotkey → speak → release → transcribed text is pasted.

Dependencies:
    pip install faster-whisper pyperclip pynput rumps
    brew install sox
"""

import subprocess, tempfile, os, time, threading, ctypes, json, sys
import pyperclip, rumps
from pynput import keyboard
from faster_whisper import WhisperModel

# ── Single-instance lock ──────────────────────────────────────────────────────
LOCK_FILE = "/tmp/whisper_dictation.lock"

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return False
        except (ProcessLookupError, ValueError, OSError):
            pass
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True

def release_lock():
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass

# ── Persistent config ─────────────────────────────────────────────────────────
CONFIG_FILE    = os.path.expanduser("~/.whisper_dictation.json")
MODEL_SIZE     = "base.en"
SAMPLE_RATE    = 16000
DEFAULT_HOTKEY = "ctrl_r"

FRIENDLY_NAMES = {
    "ctrl_r": "Right Control", "ctrl_l": "Left Control",
    "alt_r":  "Right Option",  "alt_l":  "Left Option",
    "shift_r":"Right Shift",   "shift_l": "Left Shift",
    "cmd_r":  "Right Command", "cmd_l":  "Left Command",
    **{f"f{i}": f"F{i}" for i in range(1, 13)},
}

def key_to_str(key):
    if isinstance(key, keyboard.Key):
        return key.name
    if isinstance(key, keyboard.KeyCode) and key.char:
        return f"char:{key.char}"
    return None

def str_to_key(s):
    if s.startswith("char:"):
        return keyboard.KeyCode.from_char(s[5:])
    try:
        return keyboard.Key[s]
    except KeyError:
        return keyboard.Key[DEFAULT_HOTKEY]

def friendly(key):
    s = key_to_str(key)
    if s and s.startswith("char:"):
        return s[5:].upper()
    return FRIENDLY_NAMES.get(s, s or str(key))

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
        return str_to_key(data.get("hotkey", DEFAULT_HOTKEY)), data.get("toggle_mode", False)
    except Exception:
        return str_to_key(DEFAULT_HOTKEY), False

def save_config(key, toggle_mode):
    try:
        s = key_to_str(key)
        if s:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"hotkey": s, "toggle_mode": toggle_mode}, f)
    except Exception:
        pass

def open_privacy_pane(pane):
    url = f"x-apple.systempreferences:com.apple.preference.security?{pane}"
    subprocess.Popen(["open", url])

# ── CoreGraphics Cmd+V injection (thread-safe, no osascript) ──────────────────
_cg = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
_cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
_cg.CGEventSetFlags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
_cg.CGEventPost.argtypes     = [ctypes.c_uint32, ctypes.c_void_p]
_cg.CFRelease.argtypes       = [ctypes.c_void_p]

def type_text(text):
    if not text:
        return
    prev = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.1)
    for down in (True, False):
        ev = _cg.CGEventCreateKeyboardEvent(None, 0x09, down)
        _cg.CGEventSetFlags(ev, 0x100000)
        _cg.CGEventPost(0, ev)
        _cg.CFRelease(ev)
    time.sleep(0.1)
    pyperclip.copy(prev)


class WhisperApp(rumps.App):
    def __init__(self):
        super().__init__("🎙️", quit_button="Quit")

        self.hotkey, self.toggle_mode = load_config()
        self.recording = False
        self.sox_proc  = None
        self.tmp_file  = None
        self.model     = None
        self._setting_hotkey = False

        self._status_item  = rumps.MenuItem("Status: Idle")
        self._hotkey_item  = rumps.MenuItem(f"Hotkey: {friendly(self.hotkey)}")
        self._set_hk_item  = rumps.MenuItem("Set Hotkey…", callback=self.start_set_hotkey)
        self._mode_item    = rumps.MenuItem("Toggle Mode", callback=self.toggle_mode_cb)
        self._mode_item.state = int(self.toggle_mode)

        self.menu = [
            self._status_item,
            None,
            self._hotkey_item,
            self._set_hk_item,
            self._mode_item,
            None,
            rumps.MenuItem("Show Terminal", callback=self.show_terminal),
        ]

        threading.Thread(target=self._load_model, daemon=True).start()
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set(self, status, icon=None):
        self._status_item.title = f"Status: {status}"
        if icon:
            self.title = icon

    def _request_microphone(self):
        try:
            from AVFoundation import AVCaptureDevice
            status = AVCaptureDevice.authorizationStatusForMediaType_("soun")
            if status == 0:  # Not determined — trigger system prompt
                AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                    "soun", lambda granted: None)
            elif status == 2:  # Denied — open settings
                print("Microphone access denied. Enable Terminal in System Settings → Privacy & Security → Microphone.", flush=True)
                open_privacy_pane("Privacy_Microphone")
        except Exception:
            pass

    def _load_model(self):
        self._request_microphone()
        print(f"Loading Whisper model '{MODEL_SIZE}'…", flush=True)
        self._set("Loading model…", "⏳")
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self._set("Idle", "🎙️")
        print(f"Model ready. Hold {friendly(self.hotkey)} to dictate.", flush=True)
        try:
            from AppKit import NSApplication, NSImage
            from Foundation import NSProcessInfo
            NSProcessInfo.processInfo().setProcessName_("WhisperBar")
            img = NSImage.alloc().initWithContentsOfFile_(
                '/Applications/WhisperBar.app/Contents/Resources/AppIcon.icns')
            if img:
                NSApplication.sharedApplication().setApplicationIconImage_(img)
        except Exception:
            pass

    # ── Hotkey config ─────────────────────────────────────────────────────────

    def start_set_hotkey(self, _):
        self._setting_hotkey = True
        self._set_hk_item.title = "Press any key…"
        self._set("Press new hotkey…", "⌨️")
        print("Press the key you want to use as your hotkey…", flush=True)

    def toggle_mode_cb(self, _):
        self.toggle_mode = not self.toggle_mode
        self._mode_item.state = int(self.toggle_mode)
        save_config(self.hotkey, self.toggle_mode)
        mode_name = "Toggle" if self.toggle_mode else "Hold"
        print(f"Mode set to: {mode_name}", flush=True)

    def _apply_hotkey(self, key):
        self.hotkey = key
        save_config(key, self.toggle_mode)
        name = friendly(key)
        self._hotkey_item.title = f"Hotkey: {name}"
        self._set_hk_item.title = "Set Hotkey…"
        self._set("Idle", "🎙️")
        print(f"Hotkey set to: {name}", flush=True)

    # ── Keyboard listener ─────────────────────────────────────────────────────

    def _on_press(self, key):
        if self._setting_hotkey:
            self._setting_hotkey = False
            self._apply_hotkey(key)
            return
        if key != self.hotkey or not self.model:
            return
        if self.toggle_mode:
            if not self.recording:
                self._start_recording()
            else:
                self._stop_recording()
        else:
            if not self.recording:
                self._start_recording()

    def _on_release(self, key):
        if key == self.hotkey and self.recording and not self.toggle_mode:
            self._stop_recording()

    def _start_recording(self):
        self.recording = True
        self.tmp_file  = tempfile.mktemp(suffix=".wav")
        self._set("Recording…", "🔴")
        print("● Recording…", flush=True)
        self.sox_proc = subprocess.Popen(
            ["sox", "-d", "-r", str(SAMPLE_RATE), "-c", "1", "-b", "16", self.tmp_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def _stop_recording(self):
        self.recording = False
        self.sox_proc.terminate()
        self.sox_proc.wait()
        self._set("Transcribing…", "⏳")
        print("  Transcribing…", flush=True)
        threading.Thread(target=self._transcribe, daemon=True).start()

    # ── Transcribe & paste ────────────────────────────────────────────────────

    # Hallucinations faster-whisper produces on silence
    HALLUCINATIONS = {
        "you", "you.", "thank you.", "thanks for watching.",
        "thank you for watching.", "thank you so much.", "bye.", "bye-bye.", ".", " ",
    }

    def _transcribe(self):
        try:
            segments, _ = self.model.transcribe(self.tmp_file, beam_size=5, language="en")
            text = " ".join(s.text.strip() for s in segments).strip()
            if text and text.lower() not in self.HALLUCINATIONS:
                print(f'  → "{text}"', flush=True)
                type_text(text)
                self._set(f'"{text[:50]}{"…" if len(text) > 50 else ""}"', "🎙️")
            else:
                print("  → (nothing detected)", flush=True)
                self._set("Nothing detected", "🎙️")
        except Exception as e:
            print(f"  Error: {e}", flush=True)
            self._set(f"Error: {e}", "🎙️")
        finally:
            if self.tmp_file and os.path.exists(self.tmp_file):
                os.unlink(self.tmp_file)
        time.sleep(3)
        self._set("Idle", "🎙️")

    # ── Show Terminal ─────────────────────────────────────────────────────────

    def show_terminal(self, _):
        subprocess.run(['osascript', '-e', '''
            tell application "Terminal"
                activate
                repeat with w in windows
                    if contents of w contains "whisper_statusbar" then
                        set miniaturized of w to false
                    end if
                end repeat
            end tell
        '''])


if __name__ == "__main__":
    if not acquire_lock():
        print("WhisperBar is already running.", flush=True)
        time.sleep(1)
        try:
            with open("/tmp/whisper_terminal_wid") as f:
                wid = f.read().strip()
            subprocess.run(['osascript', '-e',
                f'tell application "Terminal" to close (first window whose id is {wid})'])
        except Exception:
            pass
        sys.exit(0)
    try:
        WhisperApp().run()
    finally:
        release_lock()
