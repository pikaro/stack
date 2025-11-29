"""Focus Manager for Cocoa (macOS) applications."""

from Cocoa import (
    NSApplication,
    NSApplicationActivateIgnoringOtherApps,
    NSApplicationActivationPolicyAccessory,
    NSRunningApplication,
    NSWorkspace,
)


class FocusManagerCocoa:
    """A placeholder Focus Manager for Cocoa applications on macOS."""

    _previous_app = None

    def __init__(self) -> None:
        """Initialize the FocusManager."""
        self.app_name = None
        self._app = None
        self._workspace = None
        self._bundle_id = None

    def capture_front_app(self) -> None:
        """Capture the currently frontmost application on macOS."""
        if self._workspace is None:
            _err = 'FocusManagerCocoa not started yet.'
            raise RuntimeError(_err)

        try:
            front = self._workspace.frontmostApplication()
        except Exception:
            return

        if front is None:
            return

        try:
            front_id = front.bundleIdentifier()
        except Exception:
            front_id = None

        if front_id and front_id != self._bundle_id:
            self._previous_app = front

    def start(self) -> None:
        """Late-import Cocoa frameworks - crashes otherwise."""
        self._app = NSApplication.sharedApplication()
        self._app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        self._workspace = NSWorkspace.sharedWorkspace()
        current_app = NSRunningApplication.currentApplication()
        self._bundle_id = current_app.bundleIdentifier()

    def restore_front_app(self) -> None:
        """Restore focus to the previously frontmost application on macOS."""
        if self._previous_app is not None:
            self._previous_app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
