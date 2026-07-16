import os
import sys
import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread, Event
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QTimer
from PyQt5.QtWidgets import (QApplication, QWidget, QMenu, QDesktopWidget,
                             QVBoxLayout, QAction, QSystemTrayIcon)
from PyQt5.QtGui import QIcon
from PyQt5.QtWebEngineWidgets import QWebEngineView

APP_NAME = "VedikaMascot"

# ─────────────────────── URL shortcuts ───────────────────────
KNOWN_URLS = {
    "ai tutor": "https://vyomantha-testing.vercel.app/login",
    "vyomantha": "https://vyomantha-testing.vercel.app/login",
    "tutor": "https://vyomantha-testing.vercel.app/login",
    "website": "https://vyomantha-testing.vercel.app/login",
    "login": "https://vyomantha-testing.vercel.app/login",
}

# ─────────────────────── Path helpers ───────────────────────
def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def get_exe_path():
    """Return the path to the current running executable or script."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)

def get_memory_file_path():
    """Get persistent writable location for user memory."""
    home_dir = os.path.expanduser("~")
    vedika_dir = os.path.join(home_dir, ".vedika_mascot")
    if not os.path.exists(vedika_dir):
        os.makedirs(vedika_dir, exist_ok=True)
    dest_path = os.path.join(vedika_dir, "vedika_memory.json")
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vedika_memory.json")
    if os.path.exists(local_path) and not os.path.exists(dest_path):
        try:
            import shutil
            shutil.copy2(local_path, dest_path)
        except Exception:
            pass
    return dest_path

MEMORY_FILE = get_memory_file_path()

# ─────────────────────── Autostart helpers ───────────────────────
def is_autostart_enabled():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def set_autostart(enable: bool):
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run",
                             0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{get_exe_path()}"')
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:
        print(f"Autostart error: {e}")
        return False

# ─────────────────────── Memory helpers ───────────────────────
def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"email": None, "current_progress": {}, "quizzes": [],
                "assignments": [], "chats": [], "recent_activities": []}
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"email": None, "current_progress": {}, "quizzes": [],
                "assignments": [], "chats": [], "recent_activities": []}

def save_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving memory: {e}")

# ─────────────────────── TTS Engine ───────────────────────
class TTSEngine:
    """Text-to-speech with Indian female voice preference."""
    def __init__(self):
        self._engine = None
        self.is_speaking = False
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty('rate', 165)   # Comfortable speaking pace
            self._engine.setProperty('volume', 0.95)
            self._select_voice()
        except Exception as e:
            print(f"TTS init error: {e}")

    def _select_voice(self):
        if not self._engine:
            return
        voices = self._engine.getProperty('voices')
        # Preference: Heera=Indian English female, Zira=US female, Hazel=UK female
        preferred_keywords = ['heera', 'zira', 'hazel']
        for kw in preferred_keywords:
            for v in voices:
                if kw.lower() in v.name.lower():
                    self._engine.setProperty('voice', v.id)
                    print(f"TTS Voice selected: {v.name}")
                    return
        # Fall back to first available voice
        if voices:
            self._engine.setProperty('voice', voices[0].id)
            print(f"TTS Voice fallback: {voices[0].name}")

    def speak(self, text):
        """Speak text in a background thread so UI stays responsive."""
        if not self._engine:
            return
        def _speak():
            self.is_speaking = True
            try:
                # Clean text of emojis and special chars for TTS
                clean = ''.join(c if ord(c) < 0x1F600 else ' ' for c in text)
                clean = clean.replace('🚀', '').replace('🎉', '').replace('📚', '').strip()
                self._engine.say(clean)
                self._engine.runAndWait()
            except Exception as e:
                print(f"TTS speak error: {e}")
            finally:
                self.is_speaking = False
        Thread(target=_speak, daemon=True).start()

    def stop(self):
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
        self.is_speaking = False


# ─────────────────────── Voice Listener (STT) ───────────────────────
class VoiceListener(QObject):
    """Push-to-talk voice listener. Emits result_ready when speech detected."""
    result_ready = pyqtSignal(str)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()

    def __init__(self, tts_engine: TTSEngine):
        super().__init__()
        self.tts = tts_engine
        self._active = False
        self._stop_event = Event()

    def start_listening(self):
        """Activate one-shot listen in background thread."""
        if self._active:
            return
        self._active = True
        self.listening_started.emit()
        Thread(target=self._listen_once, daemon=True).start()

    def _listen_once(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            r.energy_threshold = 800
            r.dynamic_energy_threshold = True
            r.pause_threshold = 0.8

            # Wait until Vedika stops speaking to avoid echo loop
            while self.tts.is_speaking:
                time.sleep(0.1)

            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.4)
                try:
                    audio = r.listen(source, timeout=6, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    return  # No speech — silently stop
            try:
                text = r.recognize_google(audio, language="en-IN")
                if text.strip():
                    self.result_ready.emit(text.strip())
            except sr.UnknownValueError:
                pass  # Could not understand — silent fail, no loop
            except sr.RequestError as e:
                print(f"STT API error: {e}")
        except ImportError:
            print("speech_recognition not installed")
        except Exception as e:
            print(f"Voice listen error: {e}")
        finally:
            self._active = False
            self.listening_stopped.emit()

    def is_active(self):
        return self._active


# ─────────────────────── Command Parser ───────────────────────
def parse_command(text: str):
    """
    Returns (command_type, payload) or (None, None) if not a command.
    Handles: 'open X' -> open URL
    """
    lower = text.lower().strip()
    # Open URL command
    if lower.startswith("open "):
        target = lower[5:].strip()
        for key, url in KNOWN_URLS.items():
            if key in target or target in key:
                return "open_url", (key, url)
        return "open_unknown", target
    return None, None


# ─────────────────────── Qt Signals bridge ───────────────────────
class ServerSignals(QObject):
    change_state = pyqtSignal(str)
    show_speech = pyqtSignal(str)
    speak_text = pyqtSignal(str)


# ─────────────────────── HTTP request handler ───────────────────────
class CompanionRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == '/api/activity':
            self.handle_activity()
        elif self.path == '/api/chat':
            self.handle_chat()
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/api/status':
            self.handle_status()
        else:
            self.send_response(404)
            self.end_headers()

    def handle_status(self):
        memory = load_memory()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(memory).encode('utf-8'))

    def handle_activity(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            req = json.loads(post_data.decode('utf-8'))
            email = req.get("email")
            activity_type = req.get("activity_type")
            act_data = req.get("data", {})

            memory = load_memory()
            if email:
                memory["email"] = email

            act_log = {"activity_type": activity_type, "data": act_data, "timestamp": time.time()}
            memory["recent_activities"].append(act_log)
            if len(memory["recent_activities"]) > 100:
                memory["recent_activities"] = memory["recent_activities"][-100:]

            state = "idle"
            speech = ""

            if activity_type == "progress":
                mod_id = act_data.get("module_id")
                les_id = act_data.get("lesson_id")
                if mod_id and les_id:
                    memory["current_progress"][mod_id] = les_id
                state = "thinking"
                speech = f"Moving onto {act_data.get('lesson_title', 'next lesson')}! Great progress!"

            elif activity_type == "quiz":
                topic = act_data.get("topic", "Quiz")
                score = act_data.get("score", 0)
                memory["quizzes"].append({"topic": topic, "score": score, "timestamp": time.time()})
                if score >= 80:
                    state = "dance"
                    speech = f"Wow! A score of {score} percent on the {topic} quiz! Excellent work!"
                elif score < 50:
                    state = "sad"
                    speech = f"Quiz finished with {score} percent. That was tricky, let us review the topics!"
                else:
                    state = "thinking"
                    speech = f"Completed the {topic} quiz! Keep up the practice!"

            elif activity_type == "assignment":
                title = act_data.get("title", "Assignment")
                status = act_data.get("status", "completed")
                memory["assignments"].append({"title": title, "status": status, "timestamp": time.time()})
                if status in ("submitted", "completed"):
                    state = "dance"
                    speech = f"Hooray! Submitted the assignment: {title}!"

            elif activity_type == "error":
                state = "sad"
                speech = "Oh, a coding error! Let us debug this step by step."

            save_memory(memory)

            if state != "idle":
                self.server.signals.change_state.emit(state)
            if speech:
                self.server.signals.show_speech.emit(speech)
                self.server.signals.speak_text.emit(speech)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "state": state, "speech": speech}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def handle_chat(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            req = json.loads(post_data.decode('utf-8'))
            message = req.get("message")
            email = req.get("email")

            if not message:
                self.send_response(400)
                self.end_headers()
                return

            memory = load_memory()
            user_email = email or memory.get("email") or "anonymous_student"

            progress = memory.get("current_progress", {})
            quizzes = memory.get("quizzes", [])
            quizzes_summary = ", ".join([f"{q['topic']}: {q['score']}%" for q in quizzes[-5:]]) if quizzes else "None"
            progress_summary = ", ".join([f"Module {m}: {l}" for m, l in progress.items()]) if progress else "No progress started"
            difficulties = [q['topic'] for q in quizzes if q['score'] < 60]
            difficulties_str = ", ".join(difficulties) if difficulties else "None detected yet"

            system_prompt = (
                "You are Vedika, a friendly and encouraging 2D astronaut desktop companion and AI tutor. "
                "Your goal is to guide the user in their academic activities with Socratic advice, tips, and tailored explanations.\n"
                f"User Profile:\n"
                f"- Email: {user_email}\n"
                f"- Completed Modules/Lessons: {progress_summary}\n"
                f"- Recent Quiz performance: {quizzes_summary}\n"
                f"- Struggling concepts: {difficulties_str}\n\n"
                "Personalization Guidelines:\n"
                "1. Tailor your responses to their progress and performance.\n"
                "2. Never give raw code answers directly. Use Socratic questioning and high-level logic.\n"
                "3. Keep responses compact (under 3 paragraphs). Use emojis and speak like a friendly companion."
            )

            self.server.signals.change_state.emit("thinking")
            self.server.signals.show_speech.emit("Let me think about that...")
            self.server.signals.speak_text.emit("Let me think about that...")

            gemini_response = self.call_nextjs_gemini(system_prompt, message, user_email)
            teaser = gemini_response[:80] + "..." if len(gemini_response) > 80 else gemini_response
            self.server.signals.change_state.emit("idle")
            self.server.signals.show_speech.emit(teaser)
            self.server.signals.speak_text.emit(teaser)

            memory["chats"].append({"user": message, "companion": gemini_response, "timestamp": time.time()})
            if len(memory["chats"]) > 50:
                memory["chats"] = memory["chats"][-50:]
            save_memory(memory)

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"response": gemini_response}).encode('utf-8'))
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

    def call_nextjs_gemini(self, system, user, userId):
        url = "http://localhost:3000/api/gemini"
        payload = {"system": system, "user": user, "sessionId": "vedika_desktop_companion", "userId": userId}
        try:
            import urllib.request
            req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=12) as res:
                resp_data = json.loads(res.read().decode('utf-8'))
                if 'error' in resp_data:
                    return f"Error from AI Tutor Server: {resp_data['error']}"
                return resp_data.get('text', 'I parsed the request but received no text response.')
        except Exception as e:
            return f"I could not connect to the AI Tutor server right now. Error: {e}"


class DesktopServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, signals):
        super().__init__(server_address, RequestHandlerClass)
        self.signals = signals


class ServerThread(Thread):
    def __init__(self, port, signals):
        super().__init__()
        self.port = port
        self.signals = signals
        self.daemon = True

    def run(self):
        try:
            httpd = DesktopServer(('localhost', self.port), CompanionRequestHandler, self.signals)
            print(f"Mascot API server running on http://localhost:{self.port}")
            httpd.serve_forever()
        except Exception as e:
            print(f"Error starting local server: {e}")


# ─────────────────────── WebView with drag ───────────────────────
class MascotView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self.drag_start_pos = None
        self.setStyleSheet("background: transparent;")
        self.page().setBackgroundColor(Qt.transparent)
        # Listen for JS title-based command messages
        self.page().titleChanged.connect(self._on_title_changed)

    def _on_title_changed(self, title):
        if title == '__CMD__listen' and self.parent_widget:
            self.parent_widget.toggle_voice_listen()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.globalPos() - self.parent_widget.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_start_pos is not None:
            self.parent_widget.move(event.globalPos() - self.drag_start_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start_pos = None
        super().mouseReleaseEvent(event)


# ─────────────────────── Main Mascot Window ───────────────────────
class MascotWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.tts = TTSEngine()
        self.init_ui()
        self.init_tray()

    def init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 340)  # slightly taller to fit mic button

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.view = MascotView(self)
        layout.addWidget(self.view)

        html_path = get_resource_path("mascot.html")
        self.view.load(QUrl.fromLocalFile(html_path))

        self.reset_position()

        self.reset_timer = QTimer(self)
        self.reset_timer.setSingleShot(True)
        self.reset_timer.timeout.connect(self.reset_to_idle)

        # Qt Signals bridge
        self.signals = ServerSignals()
        self.signals.change_state.connect(self.on_change_state)
        self.signals.show_speech.connect(self.on_show_speech)
        self.signals.speak_text.connect(self.tts.speak)

        # Voice listener
        self.voice_listener = VoiceListener(self.tts)
        self.voice_listener.result_ready.connect(self.on_voice_result)
        self.voice_listener.listening_started.connect(self.on_listening_start)
        self.voice_listener.listening_stopped.connect(self.on_listening_stop)

        # HTTP API server
        self.server_thread = ServerThread(7000, self.signals)
        self.server_thread.start()

        # Greet on startup
        QTimer.singleShot(2000, self._greet)

    def init_tray(self):
        """Create system tray icon for easy access and quitting."""
        ico_path = get_resource_path("vedika.ico")
        icon = QIcon(ico_path) if os.path.exists(ico_path) else self.style().standardIcon(
            self.style().SP_ComputerIcon)

        self.tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        tray_menu.setStyleSheet("""
            QMenu { background: #0f172a; color: #f1f5f9; border: 1px solid #38bdf8;
                    border-radius: 6px; padding: 4px; font-size: 12px; }
            QMenu::item { padding: 6px 18px; border-radius: 4px; }
            QMenu::item:selected { background: rgba(56,189,248,0.2); color: #38bdf8; }
            QMenu::separator { height: 1px; background: rgba(56,189,248,0.2); margin: 3px 0; }
        """)

        act_show = tray_menu.addAction("\U0001f916 Show Vedika")
        act_mic  = tray_menu.addAction("\U0001f3a4 Activate Voice")
        tray_menu.addSeparator()
        act_quit = tray_menu.addAction("\u274c Quit Vedika")

        act_show.triggered.connect(self.show)
        act_mic.triggered.connect(self.toggle_voice_listen)
        act_quit.triggered.connect(QApplication.quit)

        self.tray.setContextMenu(tray_menu)
        self.tray.setToolTip("Vedika – AI Mascot Companion")
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()

    def _greet(self):
        msg = "Hi! I am Vedika, your AI companion. Right-click me or click the mic to talk!"
        self.on_show_speech(msg)
        self.tts.speak(msg)

    def reset_position(self):
        screen = QDesktopWidget().availableGeometry()
        x = screen.width() - self.width() - 20
        y = screen.height() - self.height() - 20
        self.move(x, y)

    def on_change_state(self, state):
        self.view.page().runJavaScript(f"setMascotState('{state}');")
        if state != 'idle':
            self.reset_timer.start(8000)

    def on_show_speech(self, text):
        safe_text = text.replace("'", "\\'").replace("\n", " ")
        self.view.page().runJavaScript(f"showSpeechBubble('{safe_text}');")

    def reset_to_idle(self):
        self.view.page().runJavaScript("setMascotState('idle');")

    def trigger_say(self):
        self.view.page().runJavaScript("showQuote();")

    # ── Voice input handlers ──
    def toggle_voice_listen(self):
        if self.voice_listener.is_active():
            return  # Already listening
        self.voice_listener.start_listening()

    def on_listening_start(self):
        self.on_change_state("thinking")
        self.on_show_speech("I am listening... speak now!")
        self.view.page().runJavaScript("setListening(true);")

    def on_listening_stop(self):
        self.view.page().runJavaScript("setListening(false);")
        QTimer.singleShot(500, self.reset_to_idle)

    def on_voice_result(self, text: str):
        """Handle recognised speech — check commands first, then chat."""
        print(f"Voice input: {text}")
        cmd_type, payload = parse_command(text)

        if cmd_type == "open_url":
            name, url = payload
            webbrowser.open(url)
            resp = f"Opening {name} for you!"
            self.on_show_speech(resp)
            self.on_change_state("dance")
            self.tts.speak(resp)

        elif cmd_type == "open_unknown":
            resp = f"I do not know how to open '{payload}' yet. Try saying open AI Tutor!"
            self.on_show_speech(resp)
            self.tts.speak(resp)

        else:
            # Treat as a chat — send to memory + Gemini
            self.on_show_speech(f'You said: "{text}"')
            self.on_change_state("thinking")
            self.tts.speak("Let me think about that!")
            Thread(target=self._voice_chat, args=(text,), daemon=True).start()

    def _voice_chat(self, message: str):
        """Process voice chat through the companion logic in a background thread."""
        memory = load_memory()
        user_email = memory.get("email") or "voice_user"
        progress = memory.get("current_progress", {})
        quizzes = memory.get("quizzes", [])
        quizzes_summary = ", ".join([f"{q['topic']}: {q['score']}%" for q in quizzes[-5:]]) if quizzes else "None"
        progress_summary = ", ".join([f"Module {m}: {l}" for m, l in progress.items()]) if progress else "None"

        system_prompt = (
            "You are Vedika, a friendly, encouraging 2D astronaut desktop AI companion. "
            "Respond conversationally in 1-2 short sentences for voice. "
            "No markdown, no bullet points, no emojis. Plain spoken English only.\n"
            f"User Progress: {progress_summary}. Recent Quizzes: {quizzes_summary}."
        )

        # Try local Gemini server
        try:
            import urllib.request
            payload = json.dumps({"system": system_prompt, "user": message,
                                  "sessionId": "vedika_voice", "userId": user_email}).encode()
            req = urllib.request.Request("http://localhost:3000/api/gemini", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as res:
                data = json.loads(res.read().decode())
                reply = data.get("text", "I could not get a response.")
        except Exception:
            # Offline fallback replies
            lower = message.lower()
            if any(w in lower for w in ["hello", "hi", "hey"]):
                reply = "Hello! Great to hear from you. How can I help with your studies today?"
            elif "how are you" in lower:
                reply = "I am doing wonderfully, ready to help you learn! What topic shall we explore?"
            elif any(w in lower for w in ["help", "stuck", "confused"]):
                reply = "No worries! Tell me which concept is tricky and we will figure it out together."
            else:
                reply = f"You said: {message}. I am offline right now, but I am here to help once the AI server is running!"

        # Emit result back to main thread safely
        self.signals.show_speech.emit(reply[:80] + "..." if len(reply) > 80 else reply)
        self.signals.speak_text.emit(reply)
        self.signals.change_state.emit("idle")

        # Save to memory
        memory["chats"].append({"user": message, "companion": reply, "timestamp": time.time()})
        if len(memory["chats"]) > 50:
            memory["chats"] = memory["chats"][-50:]
        save_memory(memory)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: rgba(15,23,42,0.95); border: 1px solid rgba(56,189,248,0.5);
                    border-radius: 8px; color: #f1f5f9; padding: 5px;
                    font-family: 'Outfit', sans-serif; font-size: 13px; }
            QMenu::item { padding: 6px 20px; border-radius: 4px; }
            QMenu::item:selected { background-color: rgba(56,189,248,0.2); color: #38bdf8; }
            QMenu::separator { height: 1px; background-color: rgba(56,189,248,0.2); margin: 4px 0; }
        """)

        action_say   = menu.addAction("\U0001f4ac Say Something")
        action_mic   = menu.addAction("\U0001f3a4 Activate Voice")
        action_open  = menu.addAction("\U0001f310 Open AI Tutor")
        action_reset = menu.addAction("\U0001f504 Reset Position")
        menu.addSeparator()
        autostart_on = is_autostart_enabled()
        action_autostart = QAction(
            ("\u2705 Run at Startup (ON)" if autostart_on else "\u25ab\ufe0f Run at Startup (OFF)"), self)
        menu.addAction(action_autostart)
        menu.addSeparator()
        action_exit = menu.addAction("\u274c Exit Vedika")

        action = menu.exec_(self.mapToGlobal(event.pos()))
        if action == action_exit:
            self.tts.stop()
            QApplication.quit()
        elif action == action_reset:
            self.reset_position()
        elif action == action_say:
            self.trigger_say()
        elif action == action_mic:
            self.toggle_voice_listen()
        elif action == action_open:
            webbrowser.open(KNOWN_URLS["ai tutor"])
            self.on_show_speech("Opening AI Tutor for you!")
            self.on_change_state("dance")
            self.tts.speak("Opening AI Tutor for you!")
        elif action == action_autostart:
            new_state = not is_autostart_enabled()
            if set_autostart(new_state):
                label = "enabled" if new_state else "disabled"
                msg = f"Startup {label}! " + ("I will greet you on every login!" if new_state else "Only running when launched.")
                self.on_show_speech(msg)
                self.tts.speak(msg)

    def closeEvent(self, event):
        # Minimize to tray instead of closing
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Vedika is still running",
            "I am in your system tray. Right-click the tray icon to quit.",
            QSystemTrayIcon.Information, 3000
        )


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in tray
    window = MascotWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
