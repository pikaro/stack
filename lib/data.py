"""Data for the stack application."""

from datetime import UTC, datetime
from pathlib import Path

STORAGE_ROOT = Path().home() / '.local' / 'share' / 'stack'
STORAGE = STORAGE_ROOT / 'entries.json'
STORAGE_DONE = STORAGE_ROOT / 'done.json'
STORAGE_USAGE = STORAGE_ROOT / 'usage.json'
VIEWER_CONFIG = STORAGE_ROOT / 'viewer_config.json'
CONTROL_SOCKET = STORAGE_ROOT / 'control.sock'
TZLOCAL = datetime.now(UTC).astimezone().tzinfo
