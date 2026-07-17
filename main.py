import os
import sys
import json
import time
import platform
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QObject, QTimer, QEvent
from PyQt5.QtWidgets import (QApplication, QWidget, QMenu, QDesktopWidget,
                             QVBoxLayout, QAction, QSystemTrayIcon)
from PyQt5.QtGui import QIcon
from PyQt5.QtWebEngineWidgets import QWebEngineView

APP_NAME   = "VedikaMascot"
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX   = platform.system() == "Linux"

# Idle time in seconds before Vedika sleeps
SLEEP_TIMEOUT = 5 * 60  # 5 minutes

# ── Vyomantha LMS page URLs ──────────────────────────────────────
PAGE_URLS = {
    "ai_tutor":    "https://vyomantha-testing.vercel.app/ai-tutor",
    "dashboard":   "https://vyomantha-testing.vercel.app/dashboard",
    "grades":      "https://vyomantha-testing.vercel.app/grades",
    "assignments": "https://vyomantha-testing.vercel.app/assignments",
    "profile":     "https://vyomantha-testing.vercel.app/profile",
    "login":       "https://vyomantha-testing.vercel.app/login",
    "home":        "https://vyomantha-testing.vercel.app/",
}

KNOWN_URLS = {
    "ai tutor":    PAGE_URLS["ai_tutor"],
    "tutor":       PAGE_URLS["ai_tutor"],
    "vyomantha":   PAGE_URLS["login"],
    "website":     PAGE_URLS["login"],
    "login":       PAGE_URLS["login"],
    "dashboard":   PAGE_URLS["dashboard"],
    "grades":      PAGE_URLS["grades"],
    "assignments": PAGE_URLS["assignments"],
    "profile":     PAGE_URLS["profile"],
    "home":        PAGE_URLS["home"],
}


# ═══════════════════════════════════════════════════════════════
#   PATH + DATA DIRECTORY HELPERS
# ═══════════════════════════════════════════════════════════════

def get_resource_path(relative_path):
    """Works for both dev and PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def get_exe_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    return os.path.abspath(__file__)

def get_data_dir():
    d = os.path.join(os.path.expanduser("~"), ".vedika_mascot")
    os.makedirs(d, exist_ok=True)
    return d

def get_memory_file_path():
    dest = os.path.join(get_data_dir(), "vedika_memory.json")
    src  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vedika_memory.json")
    if os.path.exists(src) and not os.path.exists(dest):
        try:
            import shutil; shutil.copy2(src, dest)
        except Exception:
            pass
    return dest

MEMORY_FILE = get_memory_file_path()
CONFIG_FILE = os.path.join(get_data_dir(), "vedika_config.json")


# ═══════════════════════════════════════════════════════════════
#   CONFIG  (Gemini API key + settings)
# ═══════════════════════════════════════════════════════════════

def load_env():
    """Load variables from .env file into os.environ if it exists."""
    # Check current directory or executable bundle directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        base_dir = sys._MEIPASS
    env_path = os.path.join(base_dir, ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ[k.strip()] = v.strip()
        except Exception:
            pass

def load_config():
    load_env()
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        cfg["gemini_api_key"] = env_key
    elif not cfg.get("gemini_api_key"):
        cfg["gemini_api_key"] = ""
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Config save error: {e}")


# ═══════════════════════════════════════════════════════════════
#   MEMORY
# ═══════════════════════════════════════════════════════════════

def _default_memory():
    return {
        "email": None,
        "user_name": None,
        "user_age": None,
        "strengths": [],
        "weaknesses": [],
        "current_progress": {},
        "quizzes": [],
        "assignments": [],
        "chats": [],
        "recent_activities": [],
        "total_sessions": 0,
        "last_session_end": None,
    }

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return _default_memory()
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            base = _default_memory()
            base.update(data)
            return base
    except Exception:
        return _default_memory()

def save_memory(data):
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Memory save error: {e}")

def needs_onboarding():
    m = load_memory()
    return not m.get("user_name") or not m.get("user_age")


# ═══════════════════════════════════════════════════════════════
#   PLATFORM HELPERS  (Windows-only features wrapped safely)
# ═══════════════════════════════════════════════════════════════

def is_autostart_enabled():
    if not IS_WINDOWS:
        return False
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
    if not IS_WINDOWS:
        # Linux XDG autostart
        desktop_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(desktop_dir, "vedika.desktop")
        if enable:
            os.makedirs(desktop_dir, exist_ok=True)
            content = f"[Desktop Entry]\nType=Application\nName=Vedika Mascot\nExec=python3 {get_exe_path()}\nHidden=false\nNoDisplay=false\nX-GNOME-Autostart-enabled=true\n"
            try:
                with open(desktop_file, "w") as f:
                    f.write(content)
                return True
            except Exception:
                return False
        else:
            try:
                os.remove(desktop_file)
                return True
            except Exception:
                return False
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


# ═══════════════════════════════════════════════════════════════
#   AGE-AWARE TONE BUILDER
# ═══════════════════════════════════════════════════════════════

def get_age_tone(age):
    if age is None:
        return "friendly and encouraging, suitable for a high school student"
    age = int(age)
    if age <= 10:
        return "very simple words, lots of praise, very short sentences, fun emojis, like talking to a young child"
    elif age <= 13:
        return "simple and fun, relatable, like talking to a middle schooler, use emojis"
    elif age <= 17:
        return "friendly, slightly technical, peer-like tone with emojis, like talking to a high schooler"
    elif age <= 22:
        return "professional but warm, technical depth is fine, concise"
    else:
        return "professional, concise, adult vocabulary"

def build_system_prompt(memory: dict, voice_mode: bool = False) -> str:
    name      = memory.get("user_name") or "Student"
    age       = memory.get("user_age")
    tone      = get_age_tone(age)
    progress  = memory.get("current_progress", {})
    quizzes   = memory.get("quizzes", [])
    weaknesses = memory.get("weaknesses", [])
    strengths  = memory.get("strengths",  [])
    difficulties = [q["topic"] for q in quizzes if q.get("score", 100) < 60]
    quiz_str  = ", ".join(f"{q['topic']}: {q['score']}%" for q in quizzes[-5:]) or "None yet"
    prog_str  = ", ".join(f"Module {m}: Lesson {l}" for m, l in progress.items()) or "Just starting"

    cfg = load_config()
    mode = cfg.get("personality_mode", "friendly")

    mode_instructions = {
        "humorous": (
            "Personality: Humorous & Sarcastic high-school buddy. Speak like a witty friend with mild sarcasm, friendly banter, and jokes.\n"
            "Chitchat rule: If they are just chit-chatting (e.g. asking how you are doing, if you had breakfast, etc.), chat casually like a funny peer and DO NOT bring up studies, homework, or school."
        ),
        "calm": (
            "Personality: Calm, chill, and relaxed high-school age peer. Speak with a cool, lazy, peer-like vibe.\n"
            "Chitchat rule: If they are just chit-chatting, talk about relaxing, taking breaks, or chilling out. DO NOT bring up studies, homework, or school."
        ),
        "explanatory": (
            "Personality: Friendly Socratic tutor. Focus on helping them understand and learn concepts by asking guiding questions.\n"
            "Chitchat rule: Even for chat, you are friendly, but you lead them gently back to what they want to study."
        ),
        "friendly": (
            "Personality: Cheerful, warm, and highly supportive peer best friend of their age.\n"
            "Chitchat rule: If they are just chit-chatting (e.g. how are you doing, what did you eat), chat like a close buddy, ask about their day, and DO NOT talk about studies/homework at all."
        ),
        "worried": (
            "Personality: Worried, highly caring, and protective friend.\n"
            "Chitchat rule: If they are just chit-chatting, check if they are resting enough, sleeping well, or drinking water. Do not lecture them about studies."
        )
    }
    mode_prompt = mode_instructions.get(mode, mode_instructions["friendly"])

    style = "extremely brief (maximum 1 or 2 short sentences, 15-25 words max). Keep answers to one or two lines max! Do not write paragraphs."

    return (
        f"You are Vedika, a friendly 2D astronaut desktop companion and AI friend.\n"
        f"You are talking to {name}" + (f", who is {age} years old" if age else "") + ".\n"
        f"Adjust your tone to be: {tone}.\n\n"
        f"{mode_prompt}\n\n"
        f"Student Profile:\n"
        f"- Progress: {prog_str}\n"
        f"- Recent quiz scores: {quiz_str}\n"
        f"- Topics they're struggling with: {', '.join(difficulties) if difficulties else 'None detected yet'}\n"
        f"- Strengths: {', '.join(strengths) if strengths else 'Still discovering'}\n"
        f"- Weaknesses: {', '.join(weaknesses) if weaknesses else 'None noted'}\n\n"
        f"You have a tool: navigate_to_page(page). Use it ONLY when the user clearly wants to open a page.\n"
        f"Keep responses {style}."
    )


# ═══════════════════════════════════════════════════════════════
#   GEMINI AI  (Direct API with function calling)
# ═══════════════════════════════════════════════════════════════

def call_gemini_direct(system_prompt: str, user_message: str, api_key: str, use_tools: bool = True):
    """
    Call Gemini 2.0 Flash directly using the new google-genai SDK.
    Returns dict:
      {"type": "text",          "text": "..."}
      {"type": "function_call", "name": "...", "args": {...}}
      {"type": "error",         "text": "..."}
    """
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        navigate_tool = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="navigate_to_page",
                    description=(
                        "Open a specific page of the Vyomantha LMS web app in the student's browser. "
                        "Use this when the user says 'open', 'go to', 'take me to', or 'show' a page."
                    ),
                    parameters=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "page": types.Schema(
                                type=types.Type.STRING,
                                description=(
                                    "The page name. One of: ai_tutor, dashboard, "
                                    "grades, assignments, profile, login, home"
                                ),
                            )
                        },
                        required=["page"],
                    ),
                )
            ]
        )

        config_kwargs = {
            "system_instruction": system_prompt,
        }
        if use_tools:
            config_kwargs["tools"] = [navigate_tool]

        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=user_message,
            config=types.GenerateContentConfig(**config_kwargs),
        )

        # Check for function call parts
        for part in response.candidates[0].content.parts:
            if part.function_call:
                fc = part.function_call
                return {
                    "type": "function_call",
                    "name": fc.name,
                    "args": dict(fc.args) if fc.args else {},
                }

        return {"type": "text", "text": response.text}

    except ImportError:
        return {"type": "error", "text": "google-genai not installed. Run: pip install google-genai"}
    except Exception as e:
        err = str(e)
        print(f"Gemini direct error: {err}")
        if "RESOURCE_EXHAUSTED" in err or "429" in err:
            return {"type": "error", "text": "Gemini API quota exceeded (Rate Limit / 429). Please wait a moment or check your Google AI Studio plan."}
        if any(k in err for k in ("API_KEY", "api_key", "401", "403", "invalid", "PERMISSION_DENIED")):
            return {"type": "error", "text": "Invalid or missing Gemini API key. Please check your settings."}
        return {"type": "error", "text": err}


def call_lms_server(system_prompt: str, user_message: str, user_id: str) -> str:
    """Fallback: Vyomantha Next.js /api/gemini endpoint."""
    try:
        import urllib.request
        payload = json.dumps({
            "system": system_prompt, "user": user_message,
            "sessionId": "vedika_desktop", "userId": user_id,
        }).encode("utf-8")
        req = urllib.request.Request(
            "http://localhost:3000/api/gemini", data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
            return data.get("text", "")
    except Exception:
        return ""

_OFFLINE = [
    (["hello", "hi", "hey"],                "Hello! Great to hear from you. How can I help with your studies? 😊"),
    (["how are you"],                        "Doing wonderfully! Ready to help you learn! 🚀"),
    (["help", "stuck", "confused", "don't understand"],
                                              "No worries! Tell me which concept is tricky and we'll figure it out together! 💪"),
    (["thank"],                              "You're welcome! Keep up the great work! 🌟"),
    (["bye", "goodbye"],                     "Goodbye! Keep studying hard! See you soon! 👋"),
    (["open", "go to", "take me to", "show"],
                                              "I can open pages for you! Try saying: 'Open AI Tutor' or 'Open Dashboard'."),
]

def offline_reply(message: str) -> str:
    lower = message.lower()
    for keywords, reply in _OFFLINE:
        if any(k in lower for k in keywords):
            return reply
    return "I'm offline right now, but I'm here to help once the AI service is running! Try again in a moment. 🔄"

def handle_gemini_result(result: dict, signals, voice_mode: bool = False):
    """Dispatch a Gemini result dict — opens pages or emits text."""
    if result["type"] == "function_call":
        if result["name"] == "navigate_to_page":
            page = result["args"].get("page", "ai_tutor")
            url  = PAGE_URLS.get(page, PAGE_URLS["login"])
            webbrowser.open(url)
            label = page.replace("_", " ").title()
            msg = f"Opening {label} for you! 🚀"
            signals.show_speech.emit(msg)
            signals.speak_text.emit(f"Opening {label} for you!")
            signals.change_state.emit("dance")
        return True
    return False


# ═══════════════════════════════════════════════════════════════
#   TTS ENGINE
# ═══════════════════════════════════════════════════════════════

class TTSEngine:
    def __init__(self):
        self._engine   = None
        self.is_speaking = False
        self._init_engine()

    def _init_engine(self):
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", 165)
            self._engine.setProperty("volume", 0.95)
            self._select_voice()
        except Exception as e:
            print(f"TTS init error: {e}")

    def _select_voice(self):
        if not self._engine:
            return
        voices   = self._engine.getProperty("voices")
        keywords = ["heera", "zira", "hazel", "female"]
        for kw in keywords:
            for v in voices:
                if kw.lower() in v.name.lower():
                    self._engine.setProperty("voice", v.id)
                    print(f"TTS voice: {v.name}")
                    return
        if voices:
            self._engine.setProperty("voice", voices[0].id)

    def speak(self, text: str):
        if not self._engine:
            return
        def _run():
            self.is_speaking = True
            try:
                # Strip emoji codepoints for cleaner TTS
                clean = "".join(c if ord(c) < 0x1F300 else " " for c in text).strip()
                self._engine.say(clean)
                self._engine.runAndWait()
            except Exception as e:
                print(f"TTS speak error: {e}")
            finally:
                self.is_speaking = False
        Thread(target=_run, daemon=True).start()

    def stop(self):
        if self._engine:
            try:
                self._engine.stop()
            except Exception:
                pass
        self.is_speaking = False


# ═══════════════════════════════════════════════════════════════
#   VOICE LISTENER  (push-to-talk)
# ═══════════════════════════════════════════════════════════════

class VoiceListener(QObject):
    result_ready      = pyqtSignal(str)
    listening_started = pyqtSignal()
    listening_stopped = pyqtSignal()
    no_mic_signal     = pyqtSignal()     # emitted once when no mic detected

    def __init__(self, tts: TTSEngine):
        super().__init__()
        self.tts           = tts
        self._active       = False
        self.mic_available = None   # None = unchecked, True/False after first use

    def check_mic(self) -> bool:
        """Quick synchronous check for a default input device."""
        try:
            import speech_recognition as sr
            # This raises OSError/IOError if no device is present
            with sr.Microphone():
                pass
            self.mic_available = True
        except Exception:
            self.mic_available = False
        return self.mic_available

    def start_listening(self):
        if self._active:
            return
        # If mic was already confirmed unavailable, bail immediately
        if self.mic_available is False:
            self.no_mic_signal.emit()
            return
        self._active = True
        self.listening_started.emit()
        Thread(target=self._listen_once, daemon=True).start()

    def _listen_once(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            r.energy_threshold         = 800
            r.dynamic_energy_threshold = True
            r.pause_threshold          = 0.8
            # Wait until TTS finishes to avoid echo
            while self.tts.is_speaking:
                time.sleep(0.1)
            with sr.Microphone() as source:
                self.mic_available = True
                r.adjust_for_ambient_noise(source, duration=0.4)
                try:
                    audio = r.listen(source, timeout=6, phrase_time_limit=12)
                except sr.WaitTimeoutError:
                    return
            try:
                text = r.recognize_google(audio, language="en-IN")
                if text.strip():
                    self.result_ready.emit(text.strip())
            except sr.UnknownValueError:
                pass
            except sr.RequestError as e:
                print(f"STT API error: {e}")
        except ImportError:
            print("speech_recognition not installed. Run: pip install SpeechRecognition pyaudio")
        except Exception as e:
            err = str(e)
            print(f"Voice listener error: {e}")
            # Detect missing microphone — mark permanently unavailable
            if any(k in err.lower() for k in (
                "no default input", "invalid input device",
                "no input devices", "portaudio", "device unavailable"
            )):
                self.mic_available = False
                self.no_mic_signal.emit()
        finally:
            self._active = False
            self.listening_stopped.emit()

    def is_active(self):
        return self._active


# ═══════════════════════════════════════════════════════════════
#   QT SIGNAL BRIDGE
# ═══════════════════════════════════════════════════════════════

class AppSignals(QObject):
    change_state    = pyqtSignal(str)
    show_speech     = pyqtSignal(str)
    speak_text      = pyqtSignal(str)
    record_activity = pyqtSignal()       # reset sleep timer
    save_chat       = pyqtSignal(str, str)  # (user_msg, ai_reply)


# ═══════════════════════════════════════════════════════════════
#   HTTP REQUEST HANDLER  (port 7000)
# ═══════════════════════════════════════════════════════════════

class CompanionRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress console noise

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/status":
            self._send_json(load_memory())
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        routes = {
            "/api/activity": self._handle_activity,
            "/api/chat":     self._handle_chat,
            "/api/onboard":  self._handle_onboard,
        }
        fn = routes.get(self.path)
        if fn:
            fn()
        else:
            self.send_response(404); self.end_headers()

    # ── helpers ──────────────────────────────────────────────
    def _read_json(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    @property
    def _sig(self):
        return self.server.signals

    # ── /api/onboard ─────────────────────────────────────────
    def _handle_onboard(self):
        try:
            req    = self._read_json()
            memory = load_memory()
            memory["user_name"] = req.get("name", "Student").strip() or "Student"
            memory["user_age"]  = int(req.get("age", 16))
            save_memory(memory)
            cfg = load_config()
            if req.get("apiKey"):
                cfg["gemini_api_key"] = req["apiKey"].strip()
                save_config(cfg)
            self._sig.record_activity.emit()
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    # ── /api/activity ─────────────────────────────────────────
    def _handle_activity(self):
        try:
            req           = self._read_json()
            email         = req.get("email")
            activity_type = req.get("activity_type")
            act_data      = req.get("data", {})
            memory        = load_memory()
            if email:
                memory["email"] = email
            memory["recent_activities"].append({
                "activity_type": activity_type,
                "data": act_data,
                "timestamp": time.time(),
            })
            if len(memory["recent_activities"]) > 100:
                memory["recent_activities"] = memory["recent_activities"][-100:]

            state, speech = "idle", ""

            if activity_type == "progress":
                mid = act_data.get("module_id")
                lid = act_data.get("lesson_id")
                if mid and lid:
                    memory["current_progress"][mid] = lid
                state  = "thinking"
                speech = f"Moving on to {act_data.get('lesson_title', 'the next lesson')}! Great progress! 🚀"

            elif activity_type == "quiz":
                topic = act_data.get("topic", "Quiz")
                score = act_data.get("score", 0)
                memory["quizzes"].append({"topic": topic, "score": score, "timestamp": time.time()})
                if score >= 80:
                    state  = "dance"
                    speech = f"Wow! {score}% on {topic}! You're amazing! 🎉"
                    if topic not in memory.get("strengths", []):
                        memory.setdefault("strengths", []).append(topic)
                elif score < 50:
                    state  = "sad"
                    speech = f"Got {score}% on {topic}. Let's review it together! 💪"
                    if topic not in memory.get("weaknesses", []):
                        memory.setdefault("weaknesses", []).append(topic)
                else:
                    state  = "thinking"
                    speech = f"{score}% on {topic}! Keep practising! 📚"

            elif activity_type == "assignment":
                title  = act_data.get("title", "Assignment")
                status = act_data.get("status", "completed")
                memory["assignments"].append({"title": title, "status": status, "timestamp": time.time()})
                if status in ("submitted", "completed"):
                    state  = "dance"
                    speech = f"Submitted '{title}'! Well done! 🌟"

            elif activity_type == "error":
                state  = "sad"
                speech = "Got a coding error? Let's debug it step by step! 🔧"

            save_memory(memory)
            self._sig.record_activity.emit()
            if state != "idle":
                self._sig.change_state.emit(state)
            if speech:
                self._sig.show_speech.emit(speech)
                self._sig.speak_text.emit(speech)

            self._send_json({"ok": True, "state": state, "speech": speech})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)

    # ── /api/chat ─────────────────────────────────────────────
    def _handle_chat(self):
        try:
            req     = self._read_json()
            message = req.get("message", "").strip()
            email   = req.get("email")
            if not message:
                self._send_json({"error": "Empty message"}, 400)
                return

            memory = load_memory()
            if email:
                memory["email"] = email
            uid = email or memory.get("email") or "anonymous"

            self._sig.change_state.emit("thinking")
            self._sig.show_speech.emit("Let me think about that... 🤔")
            self._sig.record_activity.emit()

            system_prompt = build_system_prompt(memory)
            cfg     = load_config()
            api_key = cfg.get("gemini_api_key", "")
            reply   = ""

            if api_key:
                result = call_gemini_direct(system_prompt, message, api_key)
                if handle_gemini_result(result, self._sig):
                    # It was a navigation — craft spoken reply
                    page  = result.get("args", {}).get("page", "ai_tutor")
                    reply = f"Navigating to {page.replace('_', ' ')} for you! 🚀"
                elif result["type"] == "text":
                    reply = result["text"]
                    self._sig.change_state.emit("idle")
                elif result["type"] == "error":
                    reply = result["text"]
                    self._sig.change_state.emit("sad")

            if not reply:
                reply = call_lms_server(system_prompt, message, uid)
            if not reply:
                reply = offline_reply(message)
                self._sig.change_state.emit("idle")

            teaser = reply[:220] + "..." if len(reply) > 220 else reply
            self._sig.show_speech.emit(teaser)
            self._sig.speak_text.emit(teaser)
            self._sig.save_chat.emit(message, reply)

            self._send_json({"response": reply})
        except Exception as e:
            self._send_json({"error": str(e)}, 500)


class DesktopServer(HTTPServer):
    def __init__(self, address, handler, signals):
        super().__init__(address, handler)
        self.signals = signals

class ServerThread(Thread):
    def __init__(self, port, signals):
        super().__init__(daemon=True)
        self.port    = port
        self.signals = signals

    def run(self):
        try:
            srv = DesktopServer(("localhost", self.port), CompanionRequestHandler, self.signals)
            print(f"Vedika API → http://localhost:{self.port}")
            srv.serve_forever()
        except Exception as e:
            print(f"Server error: {e}")


# ═══════════════════════════════════════════════════════════════
#   WEBENGINE VIEW  (with drag-to-move)
# ═══════════════════════════════════════════════════════════════

class MascotView(QWebEngineView):
    """WebEngineView with robust eventFilter drag-to-move.

    Intercepts mouse events on the focusProxy focus widget before
    they are swallowed by chromium.
    """
    _DRAG_THRESHOLD = 6  # px before a move is considered a drag

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget = parent
        self._press_global = None
        self._drag_origin  = None
        self._is_dragging  = False
        self.setStyleSheet("background: transparent;")
        self.page().setBackgroundColor(Qt.transparent)
        self.page().titleChanged.connect(self._on_title)

        # Hook load finished to install event filter on the final focusProxy
        self.loadFinished.connect(self._on_load_finished)
        self._install_filter()

    def _install_filter(self):
        if self.focusProxy():
            self.focusProxy().installEventFilter(self)

    def _on_load_finished(self, ok):
        self._install_filter()

    def _on_title(self, title):
        if title == "__CMD__listen" and self.parent_widget:
            self.parent_widget.toggle_voice_listen()
            self.page().runJavaScript("document.title = 'Vedika 2D Mascot';")

    def eventFilter(self, obj, event):
        if obj == self.focusProxy():
            if event.type() == QEvent.MouseButtonPress:
                if event.button() == Qt.LeftButton:
                    self._press_global = event.globalPos()
                    self._drag_origin  = (event.globalPos()
                                          - self.parent_widget.frameGeometry().topLeft())
                    self._is_dragging  = False
            elif event.type() == QEvent.MouseMove:
                if event.buttons() == Qt.LeftButton and self._drag_origin is not None:
                    delta = (event.globalPos() - self._press_global).manhattanLength()
                    if delta >= self._DRAG_THRESHOLD:
                        self._is_dragging = True
                    if self._is_dragging:
                        self.parent_widget.move(event.globalPos() - self._drag_origin)
                        return True  # Swallow: don't let chromium see drag movements
            elif event.type() == QEvent.MouseButtonRelease:
                was_dragging = self._is_dragging
                self._press_global = None
                self._drag_origin  = None
                self._is_dragging  = False
                if was_dragging:
                    return True  # Swallow: prevent dragging from triggering page clicks
        return super().eventFilter(obj, event)


# ═══════════════════════════════════════════════════════════════
#   ONBOARDING WINDOW  (first-run setup)
# ═══════════════════════════════════════════════════════════════

class OnboardingWindow(QWidget):
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.view = QWebEngineView(self)
        self.view.setStyleSheet("background: transparent;")
        self.view.page().setBackgroundColor(Qt.transparent)
        layout.addWidget(self.view)

        html_path = get_resource_path("onboarding.html")
        self.view.load(QUrl.fromLocalFile(html_path))
        self.view.page().titleChanged.connect(self._on_title)

        # Centre on screen
        geo = QDesktopWidget().availableGeometry()
        self.move((geo.width() - self.width()) // 2,
                  (geo.height() - self.height()) // 2)

    def _on_title(self, title):
        if title.startswith("__ONBOARD__"):
            import urllib.parse
            try:
                raw  = urllib.parse.unquote(title[len("__ONBOARD__"):])
                data = json.loads(raw)
                memory = load_memory()
                memory["user_name"] = (data.get("name") or "Student").strip()
                memory["user_age"]  = int(data.get("age") or 16)
                save_memory(memory)
                cfg = load_config()
                if data.get("apiKey"):
                    cfg["gemini_api_key"] = data["apiKey"].strip()
                    save_config(cfg)
                self.finished.emit()
                self.close()
            except Exception as e:
                print(f"Onboarding parse error: {e}")


# ═══════════════════════════════════════════════════════════════
#   MAIN MASCOT WINDOW
# ═══════════════════════════════════════════════════════════════

class MascotWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.tts          = TTSEngine()
        self.is_sleeping  = False
        self.last_active  = time.time()

        self._init_ui()
        self._init_tray()

    # ─── UI setup ────────────────────────────────────────────
    def _init_ui(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = MascotView(self)
        layout.addWidget(self.view)
        self.view.load(QUrl.fromLocalFile(get_resource_path("mascot.html")))

        self._reset_position()

        # Timers
        self._state_reset_timer = QTimer(self)
        self._state_reset_timer.setSingleShot(True)
        self._state_reset_timer.timeout.connect(self._reset_to_idle)

        self._sleep_timer = QTimer(self)
        self._sleep_timer.setSingleShot(True)
        self._sleep_timer.setInterval(SLEEP_TIMEOUT * 1000)
        self._sleep_timer.timeout.connect(self._on_sleep)
        self._sleep_timer.start()

        # Signals
        self.signals = AppSignals()
        self.signals.change_state.connect(self._on_change_state)
        self.signals.show_speech.connect(self._on_show_speech)
        self.signals.speak_text.connect(self.tts.speak)
        self.signals.record_activity.connect(self._record_activity)
        self.signals.save_chat.connect(self._save_chat)

        # Voice
        self.voice = VoiceListener(self.tts)
        self.voice.result_ready.connect(self._on_voice_result)
        self.voice.listening_started.connect(self._on_listening_start)
        self.voice.listening_stopped.connect(self._on_listening_stop)
        self.voice.no_mic_signal.connect(self._on_no_mic)

        # HTTP server
        ServerThread(7000, self.signals).start()

    # ─── System tray ─────────────────────────────────────────
    def _init_tray(self):
        ico_path = get_resource_path("vedika.ico")
        icon = (QIcon(ico_path) if os.path.exists(ico_path)
                else self.style().standardIcon(self.style().SP_ComputerIcon))
        self.tray = QSystemTrayIcon(icon, self)

        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background:#0f172a; color:#f1f5f9; border:1px solid #38bdf8;
                    border-radius:6px; padding:4px; font-size:12px; }
            QMenu::item { padding:6px 18px; border-radius:4px; }
            QMenu::item:selected { background:rgba(56,189,248,0.2); color:#38bdf8; }
            QMenu::separator { height:1px; background:rgba(56,189,248,0.2); margin:3px 0; }
        """)
        a_show  = menu.addAction("🤖 Show Vedika")
        a_mic   = menu.addAction("🎤 Activate Voice")
        a_open  = menu.addAction("🌐 Open AI Tutor")
        menu.addSeparator()
        a_quit  = menu.addAction("❌ Quit Vedika")

        a_show.triggered.connect(self.show)
        a_mic.triggered.connect(self.toggle_voice_listen)
        a_open.triggered.connect(lambda: webbrowser.open(PAGE_URLS["ai_tutor"]))
        a_quit.triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.setToolTip("Vedika – AI Mascot Companion")
        self.tray.activated.connect(
            lambda r: (self.show(), self.raise_()) if r == QSystemTrayIcon.DoubleClick else None
        )
        self.tray.show()

    # ─── Greeting ────────────────────────────────────────────
    def greet(self):
        memory   = load_memory()
        name     = memory.get("user_name") or "there"
        sessions = memory.get("total_sessions", 0)
        memory["total_sessions"] = sessions + 1
        save_memory(memory)

        if sessions == 0:
            msg = f"Hi {name}! I'm Vedika, your AI companion! 🚀 Right-click me or tap the mic to talk!"
        else:
            msg = f"Welcome back, {name}! 🌟 Ready to continue your learning journey?"
        self._on_show_speech(msg)
        self.tts.speak(msg.replace("🚀","").replace("🌟",""))

    # ─── Sleep / wake ─────────────────────────────────────────
    def _record_activity(self):
        was_sleeping   = self.is_sleeping
        self.is_sleeping = False
        self.last_active = time.time()
        self._sleep_timer.start()   # restart countdown
        if was_sleeping:
            self._on_wake_up()

    def _on_sleep(self):
        if self.is_sleeping:
            return
        self.is_sleeping = True
        self.view.page().runJavaScript("setMascotState('sleep');")
        msg = "Taking a little nap... 😴 Come back when you're ready!"
        self._on_show_speech(msg)
        self.tts.speak("I am getting sleepy. Taking a little nap. Wake me when you are back!")
        self.tray.showMessage("Vedika is sleeping 💤",
                              "Click the tray or interact to wake her up!",
                              QSystemTrayIcon.Information, 6000)

    def _on_wake_up(self):
        elapsed_min = max(0, int((time.time() - self.last_active) / 60))
        self.view.page().runJavaScript("setMascotState('wake');")
        if elapsed_min >= 1:
            msg = f"Oh! You're back! 🌟 You were away for {elapsed_min} min! Let's get back to learning!"
        else:
            msg = "Oh! You're back! Let's continue! 🚀"
        self._on_show_speech(msg)
        self.tts.speak(msg.replace("🌟","").replace("🚀",""))
        QTimer.singleShot(2000, self._reset_to_idle)

    # ─── State helpers ────────────────────────────────────────
    def _on_change_state(self, state: str):
        self.view.page().runJavaScript(f"setMascotState('{state}');")
        if state not in ("idle", "sleep", "wake"):
            self._state_reset_timer.start(8000)

    def _on_show_speech(self, text: str):
        safe = text.replace("'", "\\'").replace("\n", " ")
        self.view.page().runJavaScript(f"showSpeechBubble('{safe}');")

    def _reset_to_idle(self):
        self.view.page().runJavaScript("setMascotState('idle');")

    def _reset_position(self):
        geo = QDesktopWidget().availableGeometry()
        self.move(geo.width() - self.width() - 20,
                  geo.height() - self.height() - 20)

    # ─── Voice ────────────────────────────────────────────────
    def toggle_voice_listen(self):
        self._record_activity()
        if self.voice.is_active():
            return
        # If microphone is confirmed unavailable, fall back to text input
        if self.voice.mic_available is False:
            self._open_text_input()
            return
        self.voice.start_listening()

    def _on_no_mic(self):
        """Called once when no microphone is detected."""
        self._on_show_speech("No microphone found! Type your question instead. ⌨️")
        # Open text input dialog so the user can still chat
        QTimer.singleShot(800, self._open_text_input)

    def _open_text_input(self):
        """Lightweight text-input dialog for mic-less devices."""
        from PyQt5.QtWidgets import QInputDialog
        self._record_activity()
        text, ok = QInputDialog.getText(
            self,
            "Ask Vedika",
            "Type your question:",
        )
        if ok and text.strip():
            self._on_voice_result(text.strip())

    def _on_listening_start(self):
        self._on_change_state("thinking")
        self._on_show_speech("I'm listening... speak now! 🎤")
        self.view.page().runJavaScript("setListening(true);")

    def _on_listening_stop(self):
        self.view.page().runJavaScript("setListening(false);")
        QTimer.singleShot(500, self._reset_to_idle)

    def _on_voice_result(self, text: str):
        self._record_activity()
        print(f"[Voice] {text}")
        lower = text.lower().strip()

        # ── Fast-path keyword → open URL ──
        for keyword, url in KNOWN_URLS.items():
            nav_words = ["open", "go to", "take me to", "show", "launch", "start"]
            if keyword in lower and any(w in lower for w in nav_words):
                webbrowser.open(url)
                resp = f"Opening {keyword} for you! 🚀"
                self._on_show_speech(resp)
                self._on_change_state("dance")
                self.tts.speak(f"Opening {keyword} for you!")
                return

        # ── AI chat ──
        self._on_show_speech(f'You said: "{text[:60]}"')
        self._on_change_state("thinking")
        self.tts.speak("Let me think about that!")
        Thread(target=self._voice_chat, args=(text,), daemon=True).start()

    def _voice_chat(self, message: str):
        memory        = load_memory()
        system_prompt = build_system_prompt(memory, voice_mode=True)
        cfg           = load_config()
        api_key       = cfg.get("gemini_api_key", "")
        reply         = ""

        if api_key:
            result = call_gemini_direct(system_prompt, message, api_key, use_tools=True)
            if result["type"] == "function_call":
                fn   = result["name"]
                args = result["args"]
                if fn == "navigate_to_page":
                    page  = args.get("page", "ai_tutor")
                    url   = PAGE_URLS.get(page, PAGE_URLS["login"])
                    webbrowser.open(url)
                    label = page.replace("_", " ").title()
                    reply = f"Opening {label} for you! 🚀"
                    self.signals.change_state.emit("dance")
            elif result["type"] == "text":
                reply = result["text"]
            elif result["type"] == "error":
                reply = result["text"]
                self.signals.change_state.emit("sad")

        if not reply:
            reply = call_lms_server(system_prompt, message,
                                    memory.get("email") or "voice_user")
        if not reply:
            reply = offline_reply(message)

        short = reply[:220] + "..." if len(reply) > 220 else reply
        self.signals.show_speech.emit(short)
        self.signals.speak_text.emit(short)
        self.signals.change_state.emit("idle")
        self.signals.save_chat.emit(message, reply)

    def _save_chat(self, user_msg: str, ai_reply: str):
        memory = load_memory()
        memory["chats"].append({
            "user": user_msg, "companion": ai_reply, "timestamp": time.time()
        })
        if len(memory["chats"]) > 50:
            memory["chats"] = memory["chats"][-50:]
        save_memory(memory)

    # ─── Context menu ─────────────────────────────────────────
    def contextMenuEvent(self, event):
        self._record_activity()
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:rgba(15,23,42,0.95); border:1px solid rgba(56,189,248,0.5);
                    border-radius:8px; color:#f1f5f9; padding:5px; font-size:13px; }
            QMenu::item { padding:6px 20px; border-radius:4px; }
            QMenu::item:selected { background:rgba(56,189,248,0.2); color:#38bdf8; }
            QMenu::separator { height:1px; background:rgba(56,189,248,0.2); margin:4px 0; }
        """)
        a_say    = menu.addAction("💬 Say Something")
        a_mic    = menu.addAction("🎤 Activate Voice")
        a_open   = menu.addAction("🌐 Open AI Tutor")
        a_reset  = menu.addAction("🔄 Reset Position")
        menu.addSeparator()

        # Personality Submenu
        personality_menu = menu.addMenu("🎭 Personality Mode")
        personality_menu.setStyleSheet(menu.styleSheet())
        cfg = load_config()
        current_mode = cfg.get("personality_mode", "friendly")

        modes = [
            ("friendly", "🧸 Warm & Friendly"),
            ("humorous", "😜 Humorous & Sarcastic"),
            ("calm", "😎 Calm & Relaxed"),
            ("explanatory", "🧠 Explanatory & Socratic"),
            ("worried", "😟 Worried & Caring")
        ]

        actions = []
        for code, name_lbl in modes:
            lbl_text = f"✅ {name_lbl}" if current_mode == code else f"▫️ {name_lbl}"
            a_mode = QAction(lbl_text, self)
            a_mode.setData(code)
            personality_menu.addAction(a_mode)
            actions.append(a_mode)

        menu.addSeparator()
        autostart_on = is_autostart_enabled()
        lbl = "✅ Run at Startup (ON)" if autostart_on else "▫️ Run at Startup (OFF)"
        a_auto = QAction(lbl, self)
        menu.addAction(a_auto)
        menu.addSeparator()
        a_exit   = menu.addAction("❌ Exit Vedika")

        chosen = menu.exec_(self.mapToGlobal(event.pos()))
        if chosen == a_exit:
            self._quit()
        elif chosen == a_reset:
            self._reset_position()
        elif chosen == a_say:
            self.view.page().runJavaScript("showQuote();")
        elif chosen == a_mic:
            self.toggle_voice_listen()
        elif chosen in actions:
            new_mode = chosen.data()
            cfg["personality_mode"] = new_mode
            save_config(cfg)
            greetings = {
                "friendly": "Friendly mode active! What's on your mind? 🧸",
                "humorous": "Sarcasm mode enabled. Prepare to be roasted! 😉",
                "calm": "Chill mode activated. Let's take it easy! 🧘",
                "explanatory": "Explanatory mode active. Let's learn! 🧠",
                "worried": "Caring mode active. Don't work too hard, okay? 😟"
            }
            greeting = greetings.get(new_mode, "Mode updated!")
            self._on_show_speech(greeting)
            self.tts.speak(greeting)
        elif chosen == a_open:
            webbrowser.open(PAGE_URLS["ai_tutor"])
            self._on_show_speech("Opening AI Tutor for you! 🚀")
            self._on_change_state("dance")
            self.tts.speak("Opening AI Tutor for you!")
        elif chosen == a_auto:
            new_state = not is_autostart_enabled()
            if set_autostart(new_state):
                lbl2 = "enabled" if new_state else "disabled"
                m = f"Startup {lbl2}! " + ("I'll greet you every login! 🌟" if new_state else "Only running when launched.")
                self._on_show_speech(m)
                self.tts.speak(m.replace("🌟",""))

    # ─── Window close ─────────────────────────────────────────
    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Vedika is still here! 💫",
            "I'm in the system tray. Right-click to quit.",
            QSystemTrayIcon.Information, 3000
        )

    def _quit(self):
        memory = load_memory()
        memory["last_session_end"] = time.time()
        save_memory(memory)
        self.tts.stop()
        QApplication.quit()


# ═══════════════════════════════════════════════════════════════
#   ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    mascot = MascotWindow()

    if needs_onboarding():
        onboard = OnboardingWindow()

        def _on_onboard_done():
            mascot.show()
            QTimer.singleShot(1500, mascot.greet)

        onboard.finished.connect(_on_onboard_done)
        onboard.show()
    else:
        mascot.show()
        QTimer.singleShot(2000, mascot.greet)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
