# db.py — Работа с базой данных SQLite
# Единый класс Database: создание таблиц, CRUD для каналов, видео,
# настроек обработки, очереди загрузок, пресетов, статистики.

import sqlite3
import threading
import os
import json
from datetime import datetime


DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "app.db")


class Database:
    """
    Основной класс для работы с SQLite.
    Использует row_factory=sqlite3.Row — строки возвращаются
    как dict-подобные объекты: row["title"] вместо row[0].
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")  # Лучшая производительность
        self._lock = threading.Lock()
        self._create_tables()

    # ─────────────────────────────────────────────────────────────────
    # СОЗДАНИЕ ТАБЛИЦ
    # ─────────────────────────────────────────────────────────────────

    def _commit(self):
        """Thread-safe commit."""
        with self._lock:
            self.conn.commit()

    def _create_tables(self):
        """Создаёт все таблицы при первом запуске (IF NOT EXISTS)."""
        cur = self.conn.cursor()

        # Каналы
        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                url             TEXT    NOT NULL UNIQUE,
                yt_channel_id   TEXT,
                title           TEXT,
                description     TEXT,
                thumbnail_url   TEXT,
                video_count     INTEGER DEFAULT 0,
                last_checked    TIMESTAMP,
                added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                enabled         INTEGER DEFAULT 1,
                auto_download   INTEGER DEFAULT 0
            )
        """)

        # Видео
        cur.execute("""
            CREATE TABLE IF NOT EXISTS videos (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id      INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                yt_id           TEXT    NOT NULL UNIQUE,
                title           TEXT,
                duration        INTEGER,   -- секунды
                thumbnail_url   TEXT,
                upload_date     TEXT,      -- YYYYMMDD
                status          TEXT    DEFAULT 'new',
                                           -- new | queued | downloading | downloaded
                                           -- | processing | processed | error
                file_path       TEXT,      -- путь к скачанному файлу
                error_msg       TEXT,      -- последняя ошибка, если status=error
                view_count      INTEGER DEFAULT 0,  -- просмотры с YouTube
                downloaded_at   TIMESTAMP,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Настройки обработки (отдельные для каждого канала)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS processing_settings (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id          INTEGER NOT NULL UNIQUE
                                    REFERENCES channels(id) ON DELETE CASCADE,

                -- Нарезка
                clip_duration       INTEGER DEFAULT 60,   -- секунды
                clip_enabled        INTEGER DEFAULT 0,

                -- Склейка
                merge_enabled       INTEGER DEFAULT 0,
                merge_count         INTEGER DEFAULT 3,    -- сколько клипов клеить

                -- Стекинг (видео сверху / в центре / снизу)
                stack_enabled       INTEGER DEFAULT 0,
                top_folder          TEXT,
                center_folder       TEXT,
                bottom_folder       TEXT,

                -- Выходная папка
                output_folder       TEXT,
                output_format       TEXT    DEFAULT 'mp4',

                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Миграция: добавляем view_count если его нет (для существующих БД)
        try:
            cur.execute("ALTER TABLE videos ADD COLUMN view_count INTEGER DEFAULT 0")
            self._commit()
        except Exception:
            pass  # колонка уже существует

        # Очередь загрузок
        cur.execute("""
            CREATE TABLE IF NOT EXISTS download_queue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id    INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
                priority    INTEGER DEFAULT 0,   -- выше = важнее
                status      TEXT    DEFAULT 'pending',
                             -- pending | in_progress | done | failed
                added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Пресеты (JSON-снапшот processing_settings)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS presets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT    NOT NULL UNIQUE,
                description TEXT,
                data        TEXT    NOT NULL,   -- JSON-строка с настройками
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # КАНАЛЫ
    # ─────────────────────────────────────────────────────────────────

    def add_channel(self, url: str, title: str = None,
                    yt_channel_id: str = None,
                    thumbnail_url: str = None) -> int:
        """
        Добавляет новый канал. Возвращает id новой записи.
        Если канал с таким url уже есть — возвращает его id.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO channels (url, title, yt_channel_id, thumbnail_url)
                VALUES (?, ?, ?, ?)
            """, (url, title, yt_channel_id, thumbnail_url))
            self._commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            # Канал уже существует — вернём его id
            row = cur.execute(
                "SELECT id FROM channels WHERE url = ?", (url,)
            ).fetchone()
            return row["id"] if row else None

    def get_all_channels(self) -> list:
        """Возвращает список всех каналов."""
        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT * FROM channels ORDER BY added_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_channel(self, channel_id: int) -> dict | None:
        """Возвращает канал по id или None."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT * FROM channels WHERE id = ?", (channel_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_channel(self, channel_id: int, **kwargs) -> bool:
        """
        Обновляет поля канала. Передавай именованные аргументы:
        update_channel(1, title="New Title", enabled=0)
        """
        if not kwargs:
            return False
        allowed = {"title", "yt_channel_id", "thumbnail_url", "description",
                   "video_count", "last_checked", "enabled", "auto_download"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [channel_id]
        self.conn.execute(
            f"UPDATE channels SET {set_clause} WHERE id = ?", values
        )
        self._commit()
        return True

    def delete_channel(self, channel_id: int):
        """Удаляет канал и каскадно все его видео и настройки."""
        self.conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        self._commit()

    def mark_channel_checked(self, channel_id: int):
        """Обновляет last_checked на текущее время."""
        self.conn.execute(
            "UPDATE channels SET last_checked = ? WHERE id = ?",
            (datetime.now().isoformat(), channel_id)
        )
        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # ВИДЕО
    # ─────────────────────────────────────────────────────────────────

    def add_video(self, channel_id: int, yt_id: str, title: str = None,
                  duration: int = None, thumbnail_url: str = None,
                  upload_date: str = None,
                  view_count: int = 0) -> int | None:
        """
        Добавляет видео. Если видео с таким yt_id уже есть — пропускает.
        Возвращает id новой записи или None если уже существует.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("""
                INSERT OR IGNORE INTO videos
                    (channel_id, yt_id, title, duration, thumbnail_url, upload_date, view_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (channel_id, yt_id, title, duration, thumbnail_url, upload_date, view_count))
            self._commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # Видео уже существует

    def get_videos_by_channel(self, channel_id: int,
                               status: str = None) -> list:
        """
        Возвращает видео канала. Опционально фильтрует по статусу:
        get_videos_by_channel(1, status="downloaded")
        """
        cur = self.conn.cursor()
        if status:
            rows = cur.execute(
                "SELECT * FROM videos WHERE channel_id = ? AND status = ? "
                "ORDER BY upload_date DESC",
                (channel_id, status)
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM videos WHERE channel_id = ? "
                "ORDER BY upload_date DESC",
                (channel_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_video(self, video_id: int) -> dict | None:
        """Возвращает видео по id."""
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ).fetchone()
        return dict(row) if row else None

    def video_exists(self, yt_id: str) -> bool:
        """Проверяет, есть ли видео в базе по YouTube ID."""
        row = self.conn.execute(
            "SELECT id FROM videos WHERE yt_id = ?", (yt_id,)
        ).fetchone()
        return row is not None

    def update_video_status(self, video_id: int, status: str,
                             file_path: str = None,
                             error_msg: str = None):
        """
        Обновляет статус видео.
        Допустимые статусы: new | queued | downloading | downloaded
                            | processing | processed | error
        """
        ts = datetime.now().isoformat() if status == "downloaded" else None
        self.conn.execute("""
            UPDATE videos
            SET status = ?,
                file_path = COALESCE(?, file_path),
                error_msg = ?,
                downloaded_at = COALESCE(?, downloaded_at)
            WHERE id = ?
        """, (status, file_path, error_msg, ts, video_id))
        self._commit()

    def delete_video(self, video_id: int):
        """Удаляет видео из базы (файл на диске не трогает)."""
        self.conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        self._commit()

    def get_new_videos_count(self, channel_id: int) -> int:
        """Возвращает кол-во новых (не скачанных) видео канала."""
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM videos "
            "WHERE channel_id = ? AND status = 'new'",
            (channel_id,)
        ).fetchone()
        return row["cnt"] if row else 0

    # ─────────────────────────────────────────────────────────────────
    # ОЧЕРЕДЬ ЗАГРУЗОК
    # ─────────────────────────────────────────────────────────────────

    def add_to_queue(self, video_id: int, priority: int = 0) -> int:
        """Добавляет видео в очередь загрузки."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO download_queue (video_id, priority)
            VALUES (?, ?)
        """, (video_id, priority))
        self._commit()
        # Помечаем видео как "в очереди"
        self.update_video_status(video_id, "queued")
        return cur.lastrowid

    def get_next_in_queue(self) -> dict | None:
        """Возвращает следующий элемент очереди с наивысшим приоритетом."""
        row = self.conn.execute("""
            SELECT dq.id as queue_id, dq.video_id, dq.priority,
                   v.yt_id, v.title, v.channel_id,
                   c.url as channel_url
            FROM download_queue dq
            JOIN videos v ON dq.video_id = v.id
            JOIN channels c ON v.channel_id = c.id
            WHERE dq.status = 'pending'
            ORDER BY dq.priority DESC, dq.added_at ASC
            LIMIT 1
        """).fetchone()
        return dict(row) if row else None

    def update_queue_status(self, queue_id: int, status: str):
        """Обновляет статус элемента очереди."""
        self.conn.execute(
            "UPDATE download_queue SET status = ? WHERE id = ?",
            (status, queue_id)
        )
        self._commit()

    def clear_done_queue(self):
        """Очищает завершённые и упавшие задачи из очереди."""
        self.conn.execute(
            "DELETE FROM download_queue WHERE status IN ('done', 'failed')"
        )
        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # НАСТРОЙКИ ОБРАБОТКИ
    # ─────────────────────────────────────────────────────────────────

    def get_processing_settings(self, channel_id: int) -> dict:
        """
        Возвращает настройки обработки для канала.
        Если записи нет — создаёт дефолтную и возвращает её.
        """
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT * FROM processing_settings WHERE channel_id = ?",
            (channel_id,)
        ).fetchone()
        if row:
            return dict(row)
        # Создаём дефолтные настройки
        cur.execute(
            "INSERT INTO processing_settings (channel_id) VALUES (?)",
            (channel_id,)
        )
        self._commit()
        row = cur.execute(
            "SELECT * FROM processing_settings WHERE channel_id = ?",
            (channel_id,)
        ).fetchone()
        return dict(row)

    def update_processing_settings(self, channel_id: int, **kwargs) -> bool:
        """
        Обновляет настройки обработки для канала.
        Пример: update_processing_settings(1, clip_duration=30, stack_enabled=1)
        """
        allowed = {
            "clip_duration", "clip_enabled",
            "merge_enabled", "merge_count",
            "stack_enabled", "top_folder", "center_folder", "bottom_folder",
            "output_folder", "output_format"
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        fields["updated_at"] = datetime.now().isoformat()

        # Убедимся что запись существует
        self.get_processing_settings(channel_id)

        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [channel_id]
        self.conn.execute(
            f"UPDATE processing_settings SET {set_clause} WHERE channel_id = ?",
            values
        )
        self._commit()
        return True

    # ─────────────────────────────────────────────────────────────────
    # ПРЕСЕТЫ
    # ─────────────────────────────────────────────────────────────────

    def add_preset(self, name: str, data: dict,
                   description: str = None) -> int | None:
        """
        Сохраняет пресет. data — словарь с настройками (сохраняется как JSON).
        Возвращает id или None если имя уже занято.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO presets (name, description, data)
                VALUES (?, ?, ?)
            """, (name, description, json.dumps(data, ensure_ascii=False)))
            self._commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None


    def update_preset(self, preset_id: int, name: str,
                      data: dict, description: str = None) -> bool:
        """Обновляет существующий пресет."""
        cur = self.conn.cursor()
        try:
            cur.execute("""
                UPDATE presets
                SET name=?, description=?, data=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
            """, (name, description, json.dumps(data, ensure_ascii=False), preset_id))
            self._commit()
            return cur.rowcount > 0
        except Exception:
            return False

    def get_all_presets(self) -> list:
        """Возвращает список всех пресетов (data уже распарсен в dict)."""
        rows = self.conn.execute(
            "SELECT * FROM presets ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            p = dict(r)
            p["data"] = json.loads(p["data"])
            result.append(p)
        return result

    def get_preset(self, preset_id: int) -> dict | None:
        """Возвращает один пресет по id."""
        row = self.conn.execute(
            "SELECT * FROM presets WHERE id = ?", (preset_id,)
        ).fetchone()
        if row:
            p = dict(row)
            p["data"] = json.loads(p["data"])
            return p
        return None

    def delete_preset(self, preset_id: int):
        """Удаляет пресет."""
        self.conn.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
        self._commit()

    def preset_name_exists(self, name: str) -> bool:
        """Проверяет, занято ли имя пресета."""
        row = self.conn.execute(
            "SELECT id FROM presets WHERE name = ?", (name,)
        ).fetchone()
        return row is not None

    # ─────────────────────────────────────────────────────────────────
    # СТАТИСТИКА
    # ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        """
        Возвращает общую статистику приложения.
        Используется на странице Statistics.
        """
        cur = self.conn.cursor()

        total_channels = cur.execute(
            "SELECT COUNT(*) as n FROM channels"
        ).fetchone()["n"]

        active_channels = cur.execute(
            "SELECT COUNT(*) as n FROM channels WHERE enabled = 1"
        ).fetchone()["n"]

        total_videos = cur.execute(
            "SELECT COUNT(*) as n FROM videos"
        ).fetchone()["n"]

        # Видео по статусам
        status_rows = cur.execute("""
            SELECT status, COUNT(*) as n
            FROM videos
            GROUP BY status
        """).fetchall()
        videos_by_status = {r["status"]: r["n"] for r in status_rows}

        # Кол-во видео в очереди
        queue_pending = cur.execute(
            "SELECT COUNT(*) as n FROM download_queue WHERE status = 'pending'"
        ).fetchone()["n"]

        # Топ каналов по кол-ву видео
        top_channels = cur.execute("""
            SELECT c.title, c.url, COUNT(v.id) as video_count
            FROM channels c
            LEFT JOIN videos v ON c.id = v.channel_id
            GROUP BY c.id
            ORDER BY video_count DESC
            LIMIT 5
        """).fetchall()

        return {
            "total_channels": total_channels,
            "active_channels": active_channels,
            "total_videos": total_videos,
            "videos_by_status": videos_by_status,
            "queue_pending": queue_pending,
            "top_channels": [dict(r) for r in top_channels],
        }

    def get_channel_stats(self, channel_id: int) -> dict:
        """Статистика по конкретному каналу."""
        cur = self.conn.cursor()

        total = cur.execute(
            "SELECT COUNT(*) as n FROM videos WHERE channel_id = ?",
            (channel_id,)
        ).fetchone()["n"]

        status_rows = cur.execute("""
            SELECT status, COUNT(*) as n
            FROM videos
            WHERE channel_id = ?
            GROUP BY status
        """, (channel_id,)).fetchall()

        return {
            "total_videos": total,
            "by_status": {r["status"]: r["n"] for r in status_rows},
        }

    # ─────────────────────────────────────────────────────────────────
    # УТИЛИТЫ
    # ─────────────────────────────────────────────────────────────────

    def close(self):
        """Закрывает соединение с базой данных."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ─────────────────────────────────────────────────────────────────────
# Глобальный инстанс (используется во всех модулях)
# ─────────────────────────────────────────────────────────────────────

db = Database()
