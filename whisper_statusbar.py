#!/usr/bin/env python3
"""
WhisperBar — macOS status bar dictation app
Hold hotkey → speak → release → transcribed text is pasted.

Dependencies:
    pip install faster-whisper pyperclip pynput rumps
    brew install sox
"""

import subprocess, tempfile, os, time, threading, ctypes, json, sys
import pyperclip, rumps
from pynput import keyboard
from faster_whisper import WhisperModel

LOG_FILE       = os.path.expanduser("~/Library/Logs/WhisperBar.log")
LOCK_FILE      = "/tmp/whisper_dictation.lock"
CONFIG_FILE    = os.path.expanduser("~/.whisper_dictation.json")
MODEL_SIZE     = "base.en"
SAMPLE_RATE    = 16000
DEFAULT_HOTKEY = "cmd_r"

# ── Log capture — feeds log file and the GUI text view ────────────────────────

class _LogCapture:
    def __init__(self, stream):
        self._stream = stream
        self._lines  = []
        self._gui_cb = None   # set to fn(str) once GUI is ready

    def write(self, s):
        self._stream.write(s)
        text = s.rstrip("\n")
        if text:
            self._lines.append(text)
            if len(self._lines) > 200:
                self._lines = self._lines[-200:]
            if self._gui_cb:
                snapshot = "\n".join(self._lines[-40:])
                cb = self._gui_cb
                try:
                    from Foundation import NSOperationQueue
                    NSOperationQueue.mainQueue().addOperationWithBlock_(
                        lambda s=snapshot: cb(s))
                except Exception:
                    pass

    def flush(self):
        self._stream.flush()

    def fileno(self):
        return self._stream.fileno()

_log = _LogCapture(sys.stdout)
sys.stdout = _log
sys.stderr = _log

# ── Single-instance lock ──────────────────────────────────────────────────────

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

# ── Config ────────────────────────────────────────────────────────────────────

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
        return str_to_key(data.get("hotkey", DEFAULT_HOTKEY)), data.get("toggle_mode", True)
    except Exception:
        return str_to_key(DEFAULT_HOTKEY), True

def save_config(key, toggle_mode):
    try:
        s = key_to_str(key)
        if s:
            with open(CONFIG_FILE, "w") as f:
                json.dump({"hotkey": s, "toggle_mode": toggle_mode}, f)
    except Exception:
        pass

def open_privacy_pane(pane):
    subprocess.Popen(["open",
        f"x-apple.systempreferences:com.apple.preference.security?{pane}"])

# ── CoreGraphics Cmd+V injection ──────────────────────────────────────────────

_cg = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
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

# ── GUI control window ────────────────────────────────────────────────────────
# ObjC class at module level — PyObjC must register it exactly once.

_gui_window      = None
_gui_record_btn  = None
_gui_hotkey_btn  = None
_gui_hold_radio  = None
_gui_toggle_radio = None
_gui_log_view    = None
_gui_delegate    = None

try:
    from AppKit import NSObject as _NSObject
    class _WBDelegate(_NSObject):
        _app = None

        def recordClicked_(self, sender):
            a = self._app
            if not a or not a.model:
                return
            if not a.recording:
                a._start_recording()
                sender.setTitle_("⏹  Click to Stop")
            else:
                a._stop_recording()
                sender.setTitle_("🎙  Click to Record")

        def hotkeyClicked_(self, sender):
            a = self._app
            if not a:
                return
            a._setting_hotkey = True
            sender.setTitle_("Press any key…")
            a._set("Press new hotkey…", "⌨️")

        def holdClicked_(self, sender):
            a = self._app
            if not a or not a.toggle_mode:
                return
            a.toggle_mode = False
            a._mode_item.state = 0
            save_config(a.hotkey, False)
            _sync_mode_radios(False)

        def toggleClicked_(self, sender):
            a = self._app
            if not a or a.toggle_mode:
                return
            a.toggle_mode = True
            a._mode_item.state = 1
            save_config(a.hotkey, True)
            _sync_mode_radios(True)

        def hideClicked_(self, sender):
            if _gui_window:
                _gui_window.orderOut_(None)

        def quitClicked_(self, sender):
            rumps.quit_application()

except Exception:
    _WBDelegate = None


def _sync_mode_radios(toggle_mode):
    if _gui_hold_radio and _gui_toggle_radio:
        _gui_hold_radio.setState_(0 if toggle_mode else 1)
        _gui_toggle_radio.setState_(1 if toggle_mode else 0)

def _update_gui_record_btn(label):
    if _gui_record_btn:
        try:
            from Foundation import NSOperationQueue
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: _gui_record_btn.setTitle_(label))
        except Exception:
            pass

def _update_gui_hotkey_btn(label):
    if _gui_hotkey_btn:
        try:
            from Foundation import NSOperationQueue
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: _gui_hotkey_btn.setTitle_(label))
        except Exception:
            pass

def _update_gui_log(text):
    if _gui_log_view:
        try:
            _gui_log_view.setString_(text)
            s = _gui_log_view.string()
            _gui_log_view.scrollRangeToVisible_((len(s), 0))
        except Exception:
            pass

def _build_control_window(app):
    """Build the floating control window. Call on main thread."""
    global _gui_window, _gui_record_btn, _gui_hotkey_btn
    global _gui_hold_radio, _gui_toggle_radio, _gui_log_view, _gui_delegate

    try:
        from AppKit import (NSWindow, NSButton, NSScrollView, NSTextView,
                            NSBox, NSFont, NSMakeRect, NSApp, NSColor,
                            NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
                            NSFloatingWindowLevel, NSBackingStoreBuffered,
                            NSButtonTypeRadio)

        W = 440  # window content width

        # ── Window ────────────────────────────────────────────────────────────
        from AppKit import NSWindowStyleMaskMiniaturizable
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(200, 200, W, 330),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable,
            NSBackingStoreBuffered, False)
        win.setTitle_("WhisperBar")
        win.setLevel_(NSFloatingWindowLevel)
        win.setReleasedWhenClosed_(False)
        cv = win.contentView()
        pad = 10
        inner = W - pad * 2  # 420

        # ── Record button  (top) ──────────────────────────────────────────────
        rec = NSButton.alloc().initWithFrame_(NSMakeRect(pad, 284, inner, 36))
        rec.setTitle_("🎙  Click to Record")
        rec.setBezelStyle_(1)

        # ── Set Hotkey button ─────────────────────────────────────────────────
        hk = NSButton.alloc().initWithFrame_(NSMakeRect(pad, 240, inner, 36))
        hk.setTitle_(f"Hotkey: {friendly(app.hotkey)}")
        hk.setBezelStyle_(1)

        # ── Hold / Toggle radio buttons ───────────────────────────────────────
        half = (inner - 8) // 2
        hold_r = NSButton.alloc().initWithFrame_(NSMakeRect(pad, 214, half, 22))
        hold_r.setTitle_("Hold to Record")
        hold_r.setButtonType_(NSButtonTypeRadio)
        hold_r.setState_(0 if app.toggle_mode else 1)

        tog_r = NSButton.alloc().initWithFrame_(NSMakeRect(pad + half + 8, 214, half, 22))
        tog_r.setTitle_("Toggle Record")
        tog_r.setButtonType_(NSButtonTypeRadio)
        tog_r.setState_(1 if app.toggle_mode else 0)

        # ── Separator ─────────────────────────────────────────────────────────
        sep_top = NSBox.alloc().initWithFrame_(NSMakeRect(pad, 206, inner, 1))
        sep_top.setBoxType_(2)

        # ── Log scroll view ───────────────────────────────────────────────────
        scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(pad, 46, inner, 156))
        scroll.setBorderType_(1)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutohidesScrollers_(True)

        tv = NSTextView.alloc().initWithFrame_(scroll.contentView().frame())
        tv.setEditable_(False)
        tv.setSelectable_(True)
        tv.setFont_(NSFont.fontWithName_size_("Menlo", 10))
        tv.setBackgroundColor_(NSColor.textBackgroundColor())
        tv.setString_("\n".join(_log._lines[-40:]))
        scroll.setDocumentView_(tv)
        s = tv.string()
        tv.scrollRangeToVisible_((len(s), 0))

        # ── Separator ─────────────────────────────────────────────────────────
        sep_bot = NSBox.alloc().initWithFrame_(NSMakeRect(pad, 38, inner, 1))
        sep_bot.setBoxType_(2)

        # ── Hide / Quit buttons (bottom row) ──────────────────────────────────
        btn_w = (inner - 8) // 2
        from AppKit import NSEventModifierFlagCommand

        hide_btn = NSButton.alloc().initWithFrame_(NSMakeRect(pad, 10, btn_w, 24))
        hide_btn.setTitle_("Hide Control Window")
        hide_btn.setBezelStyle_(1)
        hide_btn.setKeyEquivalent_("w")
        hide_btn.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)

        quit_btn = NSButton.alloc().initWithFrame_(NSMakeRect(pad + btn_w + 8, 10, btn_w, 24))
        quit_btn.setTitle_("Quit Application")
        quit_btn.setBezelStyle_(1)
        quit_btn.setKeyEquivalent_("q")
        quit_btn.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)

        # ── Wire up delegate ──────────────────────────────────────────────────
        d = _WBDelegate.alloc().init()
        d._app = app

        for btn, sel in [(rec,      "recordClicked:"),
                         (hk,       "hotkeyClicked:"),
                         (hold_r,   "holdClicked:"),
                         (tog_r,    "toggleClicked:"),
                         (hide_btn, "hideClicked:"),
                         (quit_btn, "quitClicked:")]:
            btn.setTarget_(d)
            btn.setAction_(sel)

        # ── Add subviews ──────────────────────────────────────────────────────
        for v in (rec, hk, hold_r, tog_r, sep_top, scroll, sep_bot, hide_btn, quit_btn):
            cv.addSubview_(v)

        win.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

        _gui_window      = win
        _gui_record_btn  = rec
        _gui_hotkey_btn  = hk
        _gui_hold_radio  = hold_r
        _gui_toggle_radio = tog_r
        _gui_log_view    = tv
        _gui_delegate    = d

        _log._gui_cb = _update_gui_log

    except Exception as e:
        import traceback
        print(f"Control window error: {e}", flush=True)
        traceback.print_exc()


def _show_control_window(app):
    """Show (or build) the control window. Safe to call from any thread."""
    try:
        from Foundation import NSOperationQueue
        NSOperationQueue.mainQueue().addOperationWithBlock_(
            lambda: _do_show_control_window(app))
    except Exception as e:
        print(f"GUI dispatch failed: {e}", flush=True)

def _do_show_control_window(app):
    global _gui_window
    if _gui_window is None:
        _build_control_window(app)
    else:
        try:
            from AppKit import NSApp
            _gui_window.makeKeyAndOrderFront_(None)
            NSApp.activateIgnoringOtherApps_(True)
        except Exception:
            _gui_window = None
            _build_control_window(app)


# ── Main app ──────────────────────────────────────────────────────────────────

class WhisperApp(rumps.App):
    def __init__(self):
        super().__init__("🎙️", quit_button="Quit")

        self.hotkey, self.toggle_mode = load_config()
        self.recording       = False
        self.sox_proc        = None
        self.tmp_file        = None
        self.model           = None
        self._setting_hotkey = False

        self._status_item = rumps.MenuItem("Status: Idle")
        self._hotkey_item = rumps.MenuItem(f"Hotkey: {friendly(self.hotkey)}")
        self._set_hk_item = rumps.MenuItem("Set Hotkey…", callback=self.start_set_hotkey)
        self._mode_item   = rumps.MenuItem("Toggle Mode", callback=self.toggle_mode_cb)
        self._mode_item.state = int(self.toggle_mode)

        self.menu = [
            self._status_item,
            None,
            self._hotkey_item,
            self._set_hk_item,
            self._mode_item,
            None,
            rumps.MenuItem("Show Control Window", callback=self.show_control_window),
            rumps.MenuItem("View Log", callback=self.view_log),
        ]

        threading.Thread(target=self._load_model, daemon=True).start()
        self._listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release)
        self._listener.start()

    # ── Startup ───────────────────────────────────────────────────────────────

    def _check_accessibility(self):
        try:
            appserv = ctypes.cdll.LoadLibrary(
                "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
            appserv.AXIsProcessTrusted.restype = ctypes.c_bool
            if not appserv.AXIsProcessTrusted():
                print("⚠️  Accessibility not granted — pasting won't work.", flush=True)
                print("   Go to System Settings → Privacy → Accessibility", flush=True)
                print("   and add python3, then relaunch WhisperBar.", flush=True)
                open_privacy_pane("Privacy_Accessibility")
        except Exception:
            pass

    def _request_microphone(self):
        try:
            from AVFoundation import AVCaptureDevice
            status = AVCaptureDevice.authorizationStatusForMediaType_("soun")
            if status == 0:
                AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                    "soun", lambda granted: None)
            elif status == 2:
                print("⚠️  Microphone denied. Enable in System Settings → Privacy → Microphone.", flush=True)
                open_privacy_pane("Privacy_Microphone")
        except Exception:
            pass

    def _load_model(self):
        print(f"Python: {sys.executable}", flush=True)
        self._check_accessibility()
        self._request_microphone()
        print(f"Loading Whisper model '{MODEL_SIZE}'…", flush=True)
        self._set("Loading model…", "⏳")
        self.model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        self._set("Idle", "🎙️")
        if self.toggle_mode:
            print(f"Model ready. Press {friendly(self.hotkey)} to begin dictation.", flush=True)
        else:
            print(f"Model ready. Hold {friendly(self.hotkey)} to dictate.", flush=True)
        _show_control_window(self)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set(self, status, icon=None):
        self._status_item.title = f"Status: {status}"
        if icon:
            self.title = icon

    # ── Hotkey config ─────────────────────────────────────────────────────────

    def start_set_hotkey(self, _=None):
        self._setting_hotkey = True
        self._set_hk_item.title = "Press any key…"
        self._set("Press new hotkey…", "⌨️")
        _update_gui_hotkey_btn("Press any key…")

    def toggle_mode_cb(self, _=None):
        self.toggle_mode = not self.toggle_mode
        self._mode_item.state = int(self.toggle_mode)
        save_config(self.hotkey, self.toggle_mode)
        if self.toggle_mode:
            print(f"Mode: Toggle — Press {friendly(self.hotkey)} to begin dictation.", flush=True)
        else:
            print(f"Mode: Hold — Hold {friendly(self.hotkey)} to dictate.", flush=True)
        try:
            from Foundation import NSOperationQueue
            tm = self.toggle_mode
            NSOperationQueue.mainQueue().addOperationWithBlock_(
                lambda: _sync_mode_radios(tm))
        except Exception:
            pass

    def _apply_hotkey(self, key):
        self.hotkey = key
        save_config(key, self.toggle_mode)
        name = friendly(key)
        self._hotkey_item.title = f"Hotkey: {name}"
        self._set_hk_item.title = "Set Hotkey…"
        self._set("Idle", "🎙️")
        if self.toggle_mode:
            print(f"Hotkey: {name} — Press to begin dictation.", flush=True)
        else:
            print(f"Hotkey: {name} — Hold to dictate.", flush=True)
        _update_gui_hotkey_btn(f"Hotkey: {name}")

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

    # ── Recording ─────────────────────────────────────────────────────────────

    def _start_recording(self):
        self.recording = True
        self.tmp_file  = tempfile.mktemp(suffix=".wav")
        self._set("Recording…", "🔴")
        print("● Recording…", flush=True)
        _update_gui_record_btn("⏹  Click to Stop")
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
            _update_gui_record_btn("🎙  Click to Record")
        time.sleep(3)
        self._set("Idle", "🎙️")

    # ── Menu actions ──────────────────────────────────────────────────────────

    def show_control_window(self, _=None):
        _show_control_window(self)

    def view_log(self, _):
        subprocess.Popen(["open", "-a", "Console", LOG_FILE])


if __name__ == "__main__":
    if not acquire_lock():
        print("WhisperBar is already running.", flush=True)
        sys.exit(0)
    try:
        WhisperApp().run()
    finally:
        release_lock()
