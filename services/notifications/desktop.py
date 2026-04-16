"""Desktop push notifications for significant game events.

Fires native OS notifications without external dependencies:
- Windows: PowerShell + Windows.Forms balloon tip
- macOS:   osascript
- Linux:   notify-send

Notifications run in daemon threads so they never block the sync loop.
If the OS call fails (missing binary, permissions, headless server), the
error is logged and silently swallowed — notifications are best-effort.
"""
from __future__ import annotations

import logging
import platform
import subprocess
import threading

logger = logging.getLogger(__name__)

_GAME_TITLE = "LLM Activity Game"

_POWERSHELL_TEMPLATE = """\
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Information
$n.BalloonTipIcon  = [System.Windows.Forms.ToolTipIcon]::Info
$n.BalloonTipTitle = {title!r}
$n.BalloonTipText  = {message!r}
$n.Visible = $true
$n.ShowBalloonTip(6000)
Start-Sleep -Milliseconds 6500
$n.Dispose()
"""


def _notify_windows(title: str, message: str) -> None:
    script = _POWERSHELL_TEMPLATE.format(title=title, message=message)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        timeout=10,
        capture_output=True,
        check=False,
    )


def _notify_macos(title: str, message: str) -> None:
    script = f'display notification {message!r} with title {title!r}'
    subprocess.run(["osascript", "-e", script], timeout=5, capture_output=True, check=False)


def _notify_linux(title: str, message: str) -> None:
    subprocess.run(
        ["notify-send", "--urgency=normal", "--expire-time=6000", title, message],
        timeout=5,
        capture_output=True,
        check=False,
    )


def send_desktop_notification(title: str, message: str) -> None:
    """Fire a native OS notification.  Returns immediately; notification runs in background."""
    system = platform.system()

    def _run() -> None:
        try:
            if system == "Windows":
                _notify_windows(title, message)
            elif system == "Darwin":
                _notify_macos(title, message)
            elif system == "Linux":
                _notify_linux(title, message)
            else:
                logger.debug("Desktop notifications not supported on %s", system)
        except Exception:
            logger.debug("Desktop notification failed", exc_info=True)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def notify_level_up(new_level: int) -> None:
    """Send a level-up desktop notification."""
    send_desktop_notification(
        title=f"{_GAME_TITLE} — Level Up!",
        message=f"You reached Level {new_level}! Keep going!",
    )
