"""Manage application focus on macOS using AppleScript."""

import subprocess
import threading


class FocusManagerOSAScript:
    """Manage focus on macOS to restore the previously focused app after quitting."""

    _app_name: str | None
    _thread: threading.Thread

    def __init__(self) -> None:
        """Initialize the FocusManager."""
        self._app_name: str | None = None
        self._thread = threading.Thread(target=self._get_front_app_name, args=(), daemon=True)

    def capture_front_app(self) -> None:
        """Capture the name of the currently frontmost application on macOS."""
        self._thread.start()

    def start(self) -> None:
        """Wait for the front app capture thread to finish."""
        self._thread.join()

    def restore_front_app(self) -> None:
        """Restore focus to the previously frontmost application on macOS."""
        if self._app_name:
            self._activate_app(self._app_name)

    def _run_osascript(self, script: str) -> str:
        """Run the given AppleScript and return its output as a string."""
        result = subprocess.run(
            ['/usr/bin/osascript', '-'],
            input=script.encode('utf-8'),
            capture_output=True,
            check=True,
        )
        return result.stdout.decode('utf-8').strip()

    def _get_front_app_name(self) -> None:
        """Get the name of the currently frontmost application on macOS."""
        script = """
        tell application "System Events"
            set frontApp to first process whose frontmost is true
            return name of frontApp
        end tell
        """
        self._app_name = self._run_osascript(script)

    def _activate_app(self, name: str) -> None:
        """Activate the application with the given name on macOS."""
        if not name:
            return
        script = f'tell application "{name}" to activate'
        _ = self._run_osascript(script)
