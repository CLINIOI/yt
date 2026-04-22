# yt_manager/tiktok/bridge.py — локальный HTTP-сервер для TikTok Studio
#
# Портировано из https://github.com/CLINIOI/tiktok_bridge
# Адаптировано под PyQt6: сервер запускается в QThread и может быть
# остановлен из UI.

from __future__ import annotations

import http.server
import json
import logging
import mimetypes
import os
import socketserver
import threading
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


log = logging.getLogger(__name__)

ALLOWED_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".mpg", ".mpeg"}
MAX_FILE_SIZE = 4 * 1024 * 1024 * 1024  # 4 ГБ — лимит TikTok Studio
CHUNK_SIZE = 64 * 1024


@dataclass
class BridgeConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "1224444"
    allowed_ext: set = field(default_factory=lambda: set(ALLOWED_EXT))
    max_file_size: int = MAX_FILE_SIZE


def _make_handler(config: BridgeConfig):
    """Фабрика handler-класса с замыканием на конфиг."""

    class _Handler(http.server.BaseHTTPRequestHandler):
        server_version = "TikTokBridge/1.2"

        def log_message(self, fmt, *args):
            # Глушим стандартный stderr-лог — пишем через logging
            return

        # ---------- helpers ----------
        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers",
                             "X-Token, Content-Type, Range")
            self.send_header("Access-Control-Expose-Headers",
                             "Content-Length, Content-Range")

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _check_token(self) -> bool:
            token = self.headers.get("X-Token", "")
            if token != config.token:
                log.warning("bridge: invalid token from %s", self.address_string())
                self._json(403, {"error": "Invalid token"})
                return False
            return True

        def _validate_path(self, raw: str):
            if not raw:
                return False, "", "No path provided"
            if "\x00" in raw:
                return False, "", "Invalid path"
            try:
                abs_path = os.path.abspath(raw)
            except Exception as e:
                return False, "", f"Bad path: {e}"
            if not os.path.isfile(abs_path):
                return False, abs_path, "File not found"
            ext = os.path.splitext(abs_path)[1].lower()
            if ext and ext not in config.allowed_ext:
                return False, abs_path, f"Extension {ext!r} not allowed"
            try:
                if os.path.getsize(abs_path) > config.max_file_size:
                    return False, abs_path, "File too large"
            except OSError as e:
                return False, abs_path, f"Stat failed: {e}"
            return True, abs_path, ""

        # ---------- HTTP ----------
        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            try:
                parsed = urllib.parse.urlparse(self.path)
                path = parsed.path
                qs = urllib.parse.parse_qs(parsed.query)

                if path == "/health":
                    self._json(200, {
                        "status": "ok",
                        "bridge": "TikTok Studio Bridge v1.2 (embedded)",
                        "time": datetime.now().isoformat(timespec="seconds"),
                    })
                    return

                if not self._check_token():
                    return

                if path == "/check":
                    file_path = urllib.parse.unquote(qs.get("path", [""])[0])
                    ok, abs_path, err = self._validate_path(file_path)
                    if not ok and err == "No path provided":
                        self._json(400, {"error": err})
                        return
                    size = os.path.getsize(abs_path) if os.path.isfile(abs_path) else 0
                    self._json(200, {
                        "exists": ok,
                        "path": abs_path,
                        "size": size,
                        "error": err or None,
                    })
                    return

                if path == "/file":
                    file_path = urllib.parse.unquote(qs.get("path", [""])[0])
                    ok, abs_path, err = self._validate_path(file_path)
                    if not ok:
                        status = 400 if err in ("No path provided", "Invalid path") else 404
                        log.warning("bridge: /file %s: %s", err, file_path)
                        self._json(status, {"error": err, "path": abs_path})
                        return
                    self._serve_file(abs_path)
                    return

                self._json(404, {"error": "Unknown endpoint", "path": path})

            except Exception as e:
                log.exception("bridge: unexpected error: %s", e)
                try:
                    self._json(500, {"error": f"{type(e).__name__}: {e}"})
                except Exception:
                    pass

        def _serve_file(self, abs_path: str) -> None:
            mime_type, _ = mimetypes.guess_type(abs_path)
            if not mime_type:
                mime_type = "application/octet-stream"
            file_size = os.path.getsize(abs_path)
            filename = os.path.basename(abs_path)
            range_header = self.headers.get("Range", "")

            start = 0
            end = file_size - 1
            status = 200

            if range_header.startswith("bytes="):
                try:
                    rng = range_header[6:].split(",")[0].strip()
                    parts = rng.split("-")
                    if parts[0]:
                        start = int(parts[0])
                    if len(parts) > 1 and parts[1]:
                        end = int(parts[1])
                    if start > end or start >= file_size:
                        self.send_response(416)
                        self._cors()
                        self.send_header("Content-Range", f"bytes */{file_size}")
                        self.end_headers()
                        return
                    end = min(end, file_size - 1)
                    status = 206
                except ValueError:
                    status = 200
                    start = 0
                    end = file_size - 1

            length = end - start + 1
            self.send_response(status)
            self._cors()
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Disposition", f'inline; filename="{filename}"')
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
            self.end_headers()

            try:
                with open(abs_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(CHUNK_SIZE, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                log.info("bridge: client disconnected while serving %s", filename)
            except Exception as e:
                log.exception("bridge: stream failed for %s: %s", filename, e)

    return _Handler


class _ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class BridgeServer(QThread):
    """
    TikTok bridge-сервер, запускаемый в фоне из Qt-приложения.

    Сигналы:
        started_ok(host, port, token) — после успешного старта.
        error(msg)                    — если не удалось запустить или упал.
        stopped()                     — после штатной остановки.
    """

    started_ok = pyqtSignal(str, int, str)
    error = pyqtSignal(str)
    stopped = pyqtSignal()

    def __init__(self, config: Optional[BridgeConfig] = None, parent=None):
        super().__init__(parent)
        self.config = config or BridgeConfig()
        self._server: Optional[_ThreadedHTTPServer] = None
        self._lock = threading.Lock()

    # Публичный API ─────────────────────────────────────────────────
    def is_running(self) -> bool:
        with self._lock:
            return self._server is not None

    def stop(self):
        """Останавливает HTTP-сервер и блокирующе ждёт выхода потока."""
        with self._lock:
            srv = self._server
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
            try:
                srv.server_close()
            except Exception:
                pass
        self.wait(5000)

    # QThread ───────────────────────────────────────────────────────
    def run(self):
        try:
            handler = _make_handler(self.config)
            server = _ThreadedHTTPServer(
                (self.config.host, self.config.port), handler
            )
        except OSError as e:
            msg = f"Не удалось запустить bridge на {self.config.host}:{self.config.port} — {e}"
            log.error(msg)
            self.error.emit(msg)
            return
        except Exception as e:
            msg = f"Ошибка запуска bridge: {type(e).__name__}: {e}"
            log.exception(msg)
            self.error.emit(msg)
            return

        with self._lock:
            self._server = server

        self.started_ok.emit(self.config.host, self.config.port, self.config.token)
        log.info("bridge: started on %s:%s", self.config.host, self.config.port)

        try:
            server.serve_forever(poll_interval=0.5)
        except Exception as e:
            log.exception("bridge: serve_forever crashed: %s", e)
            self.error.emit(f"Bridge упал: {e}")
        finally:
            with self._lock:
                self._server = None
            log.info("bridge: stopped")
            self.stopped.emit()
