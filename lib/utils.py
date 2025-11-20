"""Utility functions for various common tasks."""

import colorsys
import datetime as dt
import hashlib
import json
from pathlib import Path

from lib.data import TZLOCAL


def now() -> str:
    """Return the current local time as an ISO 8601 string without microseconds."""
    return dt.datetime.now(TZLOCAL).replace(microsecond=0).isoformat()


def read_last_line(path: Path) -> str | None:
    """Read the last line of a file efficiently."""
    with path.open('rb') as f:
        _ = f.seek(0, 2)
        pointer = f.tell() - 1
        line = b''
        while pointer >= 0:
            _ = f.seek(pointer)
            char = f.read(1)
            if char == b'\n' and line:
                break
            line = char + line
            pointer -= 1
        return line.decode('utf-8').strip() if line else None


def name_to_color(name: str) -> str:
    """Generate a consistent hex color code from a given name."""
    digest = hashlib.md5(name.encode('utf-8')).digest()  # noqa: S324
    h_raw = int.from_bytes(digest[0:2], 'big')  # 0..65535
    s_raw = digest[2]  # 0..255
    v_raw = digest[3]  # 0..255

    hue = (h_raw % 360) / 360.0
    sat = 0.4 + 0.5 * (s_raw / 255.0)  # 0.4-0.9
    val = 0.5 + 0.5 * (v_raw / 255.0)  # 0.5-1.0

    r, g, b = colorsys.hsv_to_rgb(hue, sat, val)
    rgb = (int(r * 255), int(g * 255), int(b * 255))
    return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'


def load_json_array[T](path: Path, typ: type[T]) -> list[T]:
    """Load a JSON array from a file, returning an empty list if the file does not exist."""
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as f:
        return [typ(**item) for item in json.load(f)]


def parse_iso(s: str) -> dt.datetime:
    """Parse an ISO 8601 string into a datetime object."""
    return dt.datetime.fromisoformat(s)


def day_key(ts: dt.datetime) -> dt.date:
    """Return the date part of a datetime object."""
    return ts.date()


def iter_jsonl_reverse(path: Path):
    """Iterate JSONL file from the end backwards, yielding parsed dicts.

    We stop when timestamps go before a given start bound in the caller.
    """
    if not path.exists():
        return
    with path.open('rb') as f:
        _ = f.seek(0, 2)
        pos = f.tell()
        buffer = b''
        while pos > 0:
            pos -= 1
            _ = f.seek(pos)
            ch = f.read(1)
            if ch == b'\n' and buffer:
                line = buffer[::-1].decode('utf-8').strip()
                buffer = b''
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
            else:
                buffer += ch
        # First line
        if buffer:
            line = buffer[::-1].decode('utf-8').strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    return
