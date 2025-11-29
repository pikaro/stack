"""Protocol for managing application focus on macOS."""

from typing import Protocol


class FocusManager(Protocol):
    """Manage focus on macOS to restore the previously focused app after quitting."""

    def capture_front_app(self) -> None:
        """Capture the name of the currently frontmost application on macOS."""
        ...

    def start(self) -> None:
        """Wait for the front app capture thread to finish."""
        ...

    def restore_front_app(self) -> None:
        """Restore focus to the previously frontmost application on macOS."""
        ...
