import os
import shutil
import subprocess
import time
from collections import deque

# Canonical Context Categories
CONTEXT_DEV = 0       # VS Code, IDEs, Editors
CONTEXT_TERMINAL = 1  # Terminal, Bash, PowerShell
CONTEXT_BROWSER = 2   # Chrome, Firefox, Edge, Brave
CONTEXT_DOC = 3       # Docs, LibreOffice, Obsidian, Notion
CONTEXT_CHAT = 4      # Slack, Discord, Teams, Telegram
CONTEXT_GENERAL = 5   # General desktop / Other

CONTEXT_NAMES = {
    CONTEXT_DEV: "Developer/IDE",
    CONTEXT_TERMINAL: "Terminal/Shell",
    CONTEXT_BROWSER: "Web Browser",
    CONTEXT_DOC: "Document/Notes",
    CONTEXT_CHAT: "Communication",
    CONTEXT_GENERAL: "General/System",
}


class ContextDetector:
    """
    Detects active application context and desktop focus state.
    Provides OS-level semantic context to condition behavioral biometric classifiers,
    dramatically reducing false rejections during legitimate task switching.
    """

    def __init__(self, cache_ttl_seconds: float = 0.5):
        self.cache_ttl = cache_ttl_seconds
        self.last_check_time = 0.0
        self.cached_context_id = CONTEXT_GENERAL
        self.cached_app_name = "unknown"

        # Track recent window focus switches
        self.switch_history = deque(maxlen=30)
        self.last_active_window = None

        # Determine available system introspection tools
        self.has_xdotool = shutil.which("xdotool") is not None
        self.has_xprop = shutil.which("xprop") is not None
        self.is_linux = os.name == "posix"
        self.is_windows = os.name == "nt"

    def get_active_app(self) -> str:
        """Retrieves active application name with low-overhead caching."""
        now = time.time()
        if (now - self.last_check_time) < self.cache_ttl:
            return self.cached_app_name

        self.last_check_time = now
        app_name = "unknown"

        try:
            if self.is_linux:
                app_name = self._get_linux_active_app()
            elif self.is_windows:
                app_name = self._get_windows_active_app()
        except Exception:
            app_name = "unknown"

        if app_name != self.last_active_window:
            if self.last_active_window is not None:
                self.switch_history.append((now, app_name))
            self.last_active_window = app_name

        self.cached_app_name = app_name
        self.cached_context_id = self.classify_app(app_name)
        return app_name

    def get_active_context(self) -> int:
        """Returns the canonical context ID (0-5) for the active window."""
        self.get_active_app()
        return self.cached_context_id

    def get_switch_rate(self, window_seconds: float = 60.0) -> float:
        """Calculates window focus transitions per minute."""
        now = time.time()
        cutoff = now - window_seconds
        switches = [t for t, _ in self.switch_history if t >= cutoff]
        return (len(switches) / max(window_seconds, 1.0)) * 60.0

    def classify_app(self, name: str) -> int:
        """Maps an application process or class name to canonical context category."""
        low = name.lower()

        # IDEs / Dev
        if any(x in low for x in ("code", "sublime", "vim", "nvim", "pycharm", "intellij", "clion", "atom", "cursor")):
            return CONTEXT_DEV

        # Terminals
        if any(x in low for x in ("terminal", "bash", "zsh", "kitty", "alacritty", "konsole", "powershell", "cmd", "wezterm")):
            return CONTEXT_TERMINAL

        # Browsers
        if any(x in low for x in ("firefox", "chrome", "chromium", "brave", "edge", "opera", "safari", "zen")):
            return CONTEXT_BROWSER

        # Documents & Notes
        if any(x in low for x in ("obsidian", "notion", "writer", "calc", "word", "excel", "document", "pdf")):
            return CONTEXT_DOC

        # Communication
        if any(x in low for x in ("slack", "discord", "teams", "telegram", "whatsapp", "signal")):
            return CONTEXT_CHAT

        return CONTEXT_GENERAL

    def _get_linux_active_app(self) -> str:
        # Check DISPLAY / X11
        if "DISPLAY" in os.environ and self.has_xdotool:
            try:
                res = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowclassname"],
                    capture_output=True,
                    text=True,
                    timeout=0.15,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip().lower()
            except Exception:
                pass

        if "DISPLAY" in os.environ and self.has_xprop:
            try:
                res = subprocess.run(
                    ["xprop", "-root", "_NET_ACTIVE_WINDOW"],
                    capture_output=True,
                    text=True,
                    timeout=0.15,
                )
                if res.returncode == 0:
                    win_id = res.stdout.strip().split()[-1]
                    if win_id and win_id != "0x0":
                        res_class = subprocess.run(
                            ["xprop", "-id", win_id, "WM_CLASS"],
                            capture_output=True,
                            text=True,
                            timeout=0.15,
                        )
                        if res_class.returncode == 0:
                            parts = res_class.stdout.strip().split("=")
                            if len(parts) > 1:
                                return parts[1].replace('"', '').strip().lower()
            except Exception:
                pass

        return "linux_desktop"

    def _get_windows_active_app(self) -> str:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return "windows_desktop"

            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process_id = pid.value

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
            if not h_process:
                return "unknown"

            buf = ctypes.create_unicode_buffer(1024)
            size = ctypes.c_ulong(len(buf))
            import ctypes.wintypes
            kernel32.QueryFullProcessImageNameW(h_process, 0, buf, ctypes.byref(size))
            kernel32.CloseHandle(h_process)

            exe_path = buf.value
            return os.path.basename(exe_path).lower().replace(".exe", "")
        except Exception:
            return "windows_desktop"
