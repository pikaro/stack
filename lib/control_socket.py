"""Control socket for remote command execution."""

import contextlib
import socket
import threading
from collections.abc import Callable
from pathlib import Path


class ControlSocket:
    """Simple UNIX domain socket command server."""

    _path: Path
    _sock: socket.socket
    _thread: threading.Thread
    _stop_event: threading.Event
    _handlers: dict[str, Callable[[], bool]]
    _lock: threading.Lock

    def __init__(self, path: Path):
        """Initialize the CommandSocketServer."""
        self._path = path
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._thread = threading.Thread(target=self._serve, name='CommandSocketServer', daemon=True)
        self._stop_event = threading.Event()
        self._handlers = {}
        self._lock = threading.Lock()

    def register(self, verb: str, func: Callable[[], bool]) -> None:
        """Register a verb handler."""
        with self._lock:
            self._handlers[verb] = func

    def unregister(self, verb: str) -> None:
        """Remove a handler (no-op if not present)."""
        with self._lock:
            _ = self._handlers.pop(verb, None)

    def start(self, backlog: int = 5) -> None:
        """Start listening and spawn the accept loop thread."""
        # Remove old socket file if present
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.unlink(missing_ok=True)

        self._sock.bind(self._path.as_posix())
        self._sock.listen(backlog)
        self._sock.settimeout(1.0)  # so we can periodically check stop_event

        self._stop_event.clear()

        self._thread.start()

    def stop(self) -> None:
        """Stop the server and clean up resources."""
        self._stop_event.set()

        with contextlib.suppress(OSError):
            self._sock.close()

        self._thread.join(timeout=2.0)

        self._path.unlink(missing_ok=True)

    def _serve(self) -> None:
        """Main accept loop, runs in background thread."""
        assert self._sock is not None
        srv_sock = self._sock

        while not self._stop_event.is_set():
            try:
                conn, _ = srv_sock.accept()
            except TimeoutError:
                continue
            except OSError:
                # Socket was probably closed
                break

            t = threading.Thread(
                target=self._handle_client,
                args=(conn,),
                daemon=True,
            )
            t.start()

    def _handle_client(self, conn: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            # Text-mode, line-buffered I/O
            f = conn.makefile('rwb', buffering=1)
            with f, conn:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        # Ignore empty lines
                        continue

                    try:
                        verb = line.decode('utf-8')
                    except UnicodeDecodeError:
                        _ = f.write(b'ERR\n')
                        f.flush()
                        continue

                    try:
                        handler = self._get_handler(verb)
                    except KeyError:
                        _ = f.write(b'UNKNOWN\n')
                        f.flush()
                        continue

                    try:
                        result = handler()
                    except Exception:
                        # Handler blew up: treat as failure
                        result = False

                    _ = f.write(b'OK\n' if result else b'ERR\n')
                    f.flush()
        except OSError:
            # Connection broke, ignore
            pass

    def _get_handler(self, verb: str) -> Callable[[], bool]:
        with self._lock:
            ret = self._handlers.get(verb)
            if ret is not None:
                return ret
            _err = f'No handler registered for verb: {verb}'
            raise KeyError(_err)
