# db.py — Работа с базой данных SQLite
# Единый класс Database: создание таблиц, CRUD для каналов, видео,
# настроек обработки, очереди загрузок, пресетов, статистики.

import sqlite3
import threading
import os
import json
from datetime import datetime


# Определяем путь к БД строго относительно этого файла
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH   = os.path.join(_THIS_DIR, "data", "app.db")

# Гарантируем существование папки data/ при загрузке модуля
try:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
except OSError:
    pass


class Database:
    """
    Основной класс для работы с SQLite.
    Использует row_factory=sqlite3.Row — строки возвращаются
    как dict-подобные объекты: row["title"] вместо row[0].
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = os.path.abspath(db_path)
        db_dir = os.path.dirname(self.db_path)
        try:
            os.makedirs(db_dir, exist_ok=True)
        except OSError:
            pass

        # OneDrive/сетевые диски не поддерживают WAL — используем DELETE journal
        for _timeout in (5000, 15000):
            try:
                self.conn = sqlite3.connect(
                    self.db_path,
                    isolation_level=None,
                    check_same_thread=False,
                    timeout=_timeout / 1000,
                )
                self.conn.row_factory = sqlite3.Row
                self.conn.execute("PRAGMA foreign_keys = ON")
                self.conn.execute("PRAGMA journal_mode = DELETE")
                self.conn.execute("PRAGMA synchronous = NORMAL")
                break
            except Exception as _e:
                if _timeout == 15000:
                    raise OSError(
                        f"SQLite не может открыть файл: {self.db_path}\n"
                        f"Причина: {_e}\n"
                        f"Папка существует: {os.path.isdir(os.path.dirname(self.db_path))}\n"
                        f"Права на запись: {os.access(os.path.dirname(self.db_path), os.W_OK)}\n"
                        f"Совет: папка на OneDrive — перенеси проект в C:\\yt_manager\\"
                    ) from _e
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
                auto_download   INTEGER DEFAULT 0,
                tiktok_handle   TEXT,
                tiktok_url      TEXT
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

        # Миграция: TikTok поля для каналов
        try:
            cur.execute("ALTER TABLE channels ADD COLUMN tiktok_handle TEXT")
            self._commit()
        except Exception:
            pass
        try:
            cur.execute("ALTER TABLE channels ADD COLUMN tiktok_url TEXT")
            self._commit()
        except Exception:
            pass

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

        # Миграция: updated_at для пресетов
        try:
            cur.execute("ALTER TABLE presets ADD COLUMN updated_at TIMESTAMP")
            self._commit()
        except Exception:
            pass

        # ── TikTok каналы ───────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_channels (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                handle          TEXT    NOT NULL UNIQUE,
                display_name    TEXT,
                avatar_url      TEXT,
                hashtags_json   TEXT    DEFAULT '[]',
                schedule_json   TEXT    DEFAULT '[]',
                clip_min_buffer INTEGER DEFAULT 10,
                enabled         INTEGER DEFAULT 1,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Связь TikTok ↔ YouTube (N:M) ────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tiktok_youtube_link (
                tiktok_id  INTEGER NOT NULL REFERENCES tiktok_channels(id) ON DELETE CASCADE,
                youtube_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                PRIMARY KEY (tiktok_id, youtube_id)
            )
        """)

        # ── Готовые клипы ───────────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tiktok_id       INTEGER NOT NULL REFERENCES tiktok_channels(id) ON DELETE CASCADE,
                source_video_id INTEGER REFERENCES videos(id) ON DELETE SET NULL,
                file_path       TEXT    NOT NULL,
                duration        REAL,
                status          TEXT    DEFAULT 'ready',
                                 -- ready | published | removed
                generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                published_at    TIMESTAMP
            )
        """)

        # ── Скрипты публикации ──────────────────────────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS publish_scripts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tiktok_id       INTEGER NOT NULL REFERENCES tiktok_channels(id) ON DELETE CASCADE,
                clip_id         INTEGER REFERENCES clips(id) ON DELETE CASCADE,
                title           TEXT,
                file_path       TEXT,
                hashtags        TEXT,
                scheduled_at    TIMESTAMP,
                caption         TEXT,
                status          TEXT    DEFAULT 'draft',
                                 -- draft | marked | done
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Миграция: перенос channels.tiktok_handle → tiktok_channels
        #    + tiktok_youtube_link. Идемпотентно (INSERT OR IGNORE). ──
        self._migrate_tiktok_links_from_channels(cur)

        # ── Настройки автоматизации (1 к 1 с YouTube-каналом) ───────
        # Миграция: если таблица уже существует со старой схемой (tiktok_id)
        # — переносим записи на все привязанные YouTube-каналы через
        # tiktok_youtube_link, затем пересоздаём таблицу.
        self._migrate_automation_settings(cur)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS automation_settings (
                channel_id          INTEGER PRIMARY KEY
                                    REFERENCES channels(id) ON DELETE CASCADE,
                download_enabled    INTEGER DEFAULT 1,
                min_duration_sec    INTEGER DEFAULT 300,
                max_duration_sec    INTEGER DEFAULT 1800,
                max_age_days        INTEGER DEFAULT 7,
                fallback_popular    INTEGER DEFAULT 1,
                processing_enabled  INTEGER DEFAULT 1,
                banner_dir          TEXT,
                retention_dir       TEXT,
                background_dir      TEXT,
                clip_duration_sec   INTEGER DEFAULT 30,
                publish_enabled     INTEGER DEFAULT 1,
                auto_active         INTEGER DEFAULT 0,
                updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Миграция: auto_active для старых БД
        try:
            cur.execute(
                "ALTER TABLE automation_settings ADD COLUMN auto_active INTEGER DEFAULT 0"
            )
            self._commit()
        except Exception:
            pass

        # ── Приложение (ключ-значение для настроек) ─────────────────
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key         TEXT PRIMARY KEY,
                value       TEXT,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # ── Индексы ────────────────────────────────────────────────
        cur.execute("CREATE INDEX IF NOT EXISTS idx_clips_tiktok ON clips(tiktok_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_scripts_tiktok ON publish_scripts(tiktok_id, status)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel_status ON videos(channel_id, status)")

        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # МИГРАЦИИ
    # ─────────────────────────────────────────────────────────────────

    def _migrate_tiktok_links_from_channels(self, cur) -> None:
        """Переносит channels.tiktok_handle/tiktok_url в tiktok_channels
        и tiktok_youtube_link. Идемпотентно (INSERT OR IGNORE).

        Срабатывает при каждом старте — старые каналы с заполненной
        колонкой tiktok_handle получают полноценную привязку, которую
        ожидает AutomationPage.
        """
        try:
            rows = cur.execute(
                "SELECT id, tiktok_handle, tiktok_url FROM channels "
                "WHERE tiktok_handle IS NOT NULL AND tiktok_handle != ''"
            ).fetchall()
        except Exception:
            return

        for row in rows:
            ch_id = row["id"]
            raw = (row["tiktok_handle"] or "").strip().lstrip("@")
            if not raw:
                continue
            try:
                tt = cur.execute(
                    "SELECT id FROM tiktok_channels WHERE handle = ?", (raw,)
                ).fetchone()
                if tt:
                    tt_id = tt["id"]
                else:
                    cur.execute(
                        "INSERT INTO tiktok_channels(handle, display_name) "
                        "VALUES(?, ?)", (raw, raw)
                    )
                    tt_id = cur.lastrowid
                cur.execute(
                    "INSERT OR IGNORE INTO tiktok_youtube_link "
                    "(tiktok_id, youtube_id) VALUES(?, ?)",
                    (int(tt_id), int(ch_id))
                )
            except Exception as e:
                try:
                    import logging
                    logging.getLogger(__name__).warning(
                        "tiktok-link migration row id=%s skipped: %s", ch_id, e
                    )
                except Exception:
                    pass
        self.conn.commit()

    def _migrate_automation_settings(self, cur) -> None:
        """Неразрушающая миграция automation_settings: tiktok_id → channel_id.

        Если таблица уже существует со старой схемой (PK = tiktok_id),
        создаём automation_settings_new со схемой по channel_id, переносим
        данные: для каждой старой записи тянем список привязанных
        YouTube-каналов (tiktok_youtube_link) и копируем настройки на
        каждый из них. Затем DROP старой и RENAME новой.
        """
        try:
            info = cur.execute("PRAGMA table_info(automation_settings)").fetchall()
        except Exception:
            return
        if not info:
            return  # таблицы ещё нет — будет создана сразу в новой схеме
        cols = [c[1] for c in info]
        if "channel_id" in cols:
            return  # уже мигрировано
        if "tiktok_id" not in cols:
            return

        try:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS automation_settings_new (
                    channel_id          INTEGER PRIMARY KEY
                                        REFERENCES channels(id) ON DELETE CASCADE,
                    download_enabled    INTEGER DEFAULT 1,
                    min_duration_sec    INTEGER DEFAULT 300,
                    max_duration_sec    INTEGER DEFAULT 1800,
                    max_age_days        INTEGER DEFAULT 7,
                    fallback_popular    INTEGER DEFAULT 1,
                    processing_enabled  INTEGER DEFAULT 1,
                    banner_dir          TEXT,
                    retention_dir       TEXT,
                    background_dir      TEXT,
                    clip_duration_sec   INTEGER DEFAULT 30,
                    publish_enabled     INTEGER DEFAULT 1,
                    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            rows = cur.execute("SELECT * FROM automation_settings").fetchall()
            for row in rows:
                d = dict(row)
                tt_id = d.get("tiktok_id")
                if not tt_id:
                    continue
                yt_ids = [r[0] for r in cur.execute(
                    "SELECT youtube_id FROM tiktok_youtube_link WHERE tiktok_id = ?",
                    (int(tt_id),)
                ).fetchall()]
                for yt_id in yt_ids:
                    cur.execute("""
                        INSERT OR REPLACE INTO automation_settings_new (
                            channel_id, download_enabled, min_duration_sec,
                            max_duration_sec, max_age_days, fallback_popular,
                            processing_enabled, banner_dir, retention_dir,
                            background_dir, clip_duration_sec, publish_enabled,
                            updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        int(yt_id),
                        int(d.get("download_enabled") or 1),
                        int(d.get("min_duration_sec") or 300),
                        int(d.get("max_duration_sec") or 1800),
                        int(d.get("max_age_days") or 7),
                        int(d.get("fallback_popular") or 1),
                        int(d.get("processing_enabled") or 1),
                        d.get("banner_dir"),
                        d.get("retention_dir"),
                        d.get("background_dir"),
                        int(d.get("clip_duration_sec") or 30),
                        int(d.get("publish_enabled") or 1),
                        d.get("updated_at") or datetime.now().isoformat(),
                    ))

            cur.execute("DROP TABLE automation_settings")
            cur.execute("ALTER TABLE automation_settings_new RENAME TO automation_settings")
        except Exception as e:
            try:
                import logging
                logging.getLogger(__name__).exception(
                    "Миграция automation_settings не удалась: %s", e
                )
            except Exception:
                pass
            try:
                cur.execute("DROP TABLE IF EXISTS automation_settings_new")
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────
    # КАНАЛЫ
    # ─────────────────────────────────────────────────────────────────

    def add_channel(self, url: str, title: str = None,
                    yt_channel_id: str = None,
                    thumbnail_url: str = None,
                    tiktok_handle: str = None,
                    tiktok_url: str = None) -> int:
        """
        Добавляет новый канал. Возвращает id новой записи.
        Если канал с таким url уже есть — возвращает его id.
        """
        cur = self.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO channels (url, title, yt_channel_id, thumbnail_url, tiktok_handle, tiktok_url)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (url, title, yt_channel_id, thumbnail_url, tiktok_handle, tiktok_url))
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
                   "video_count", "last_checked", "enabled", "auto_download",
                   "tiktok_handle", "tiktok_url"}
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
        # Явное приведение типов — защита от float/None/нестандартных значений
        def _int_or_none(v):
            try: return int(v) if v is not None else None
            except (TypeError, ValueError): return None

        def _str_or_none(v):
            try: return str(v)[:500] if v is not None else None
            except Exception: return None

        params = (
            int(channel_id),
            str(yt_id),
            _str_or_none(title),
            _int_or_none(duration),
            _str_or_none(thumbnail_url),
            _str_or_none(upload_date),
            _int_or_none(view_count) or 0,
        )

        with self._lock:
            cur = self.conn.cursor()
            try:
                cur.execute("""
                    INSERT OR IGNORE INTO videos
                        (channel_id, yt_id, title, duration, thumbnail_url, upload_date, view_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, params)
                self.conn.commit()
                return cur.lastrowid if cur.lastrowid else None
            except sqlite3.IntegrityError:
                return None  # Видео уже существует
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(
                    "add_video failed: yt_id=%r params=%r err=%s", yt_id, params, e
                )
                return None

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
    # TIKTOK-КАНАЛЫ
    # ─────────────────────────────────────────────────────────────────

    def add_tiktok_channel(self, handle: str, display_name: str = None,
                           avatar_url: str = None,
                           clip_min_buffer: int = 10) -> int | None:
        """Создаёт TikTok-канал. Возвращает id или id существующего при коллизии handle."""
        handle = (handle or "").strip().lstrip("@")
        if not handle:
            return None
        cur = self.conn.cursor()
        try:
            cur.execute("""
                INSERT INTO tiktok_channels (handle, display_name, avatar_url, clip_min_buffer)
                VALUES (?, ?, ?, ?)
            """, (handle, display_name, avatar_url, int(clip_min_buffer or 10)))
            self._commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            row = cur.execute(
                "SELECT id FROM tiktok_channels WHERE handle = ?", (handle,)
            ).fetchone()
            return row["id"] if row else None

    def get_tiktok_channel(self, tiktok_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM tiktok_channels WHERE id = ?", (tiktok_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["hashtags"] = json.loads(d.get("hashtags_json") or "[]")
        d["schedule"] = json.loads(d.get("schedule_json") or "[]")
        return d

    def get_tiktok_channel_by_handle(self, handle: str) -> dict | None:
        handle = (handle or "").strip().lstrip("@")
        if not handle:
            return None
        row = self.conn.execute(
            "SELECT * FROM tiktok_channels WHERE handle = ?", (handle,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["hashtags"] = json.loads(d.get("hashtags_json") or "[]")
        d["schedule"] = json.loads(d.get("schedule_json") or "[]")
        return d

    def list_tiktok_channels(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM tiktok_channels ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["hashtags"] = json.loads(d.get("hashtags_json") or "[]")
            d["schedule"] = json.loads(d.get("schedule_json") or "[]")
            result.append(d)
        return result

    def update_tiktok_channel(self, tiktok_id: int, **kwargs) -> bool:
        allowed = {"handle", "display_name", "avatar_url",
                   "hashtags_json", "schedule_json",
                   "clip_min_buffer", "enabled"}
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        if not fields:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [tiktok_id]
        self.conn.execute(
            f"UPDATE tiktok_channels SET {set_clause} WHERE id = ?", values
        )
        self._commit()
        return True

    def delete_tiktok_channel(self, tiktok_id: int):
        self.conn.execute("DELETE FROM tiktok_channels WHERE id = ?", (tiktok_id,))
        self._commit()

    def set_tiktok_hashtags(self, tiktok_id: int, hashtags: list) -> bool:
        payload = json.dumps(list(hashtags or []), ensure_ascii=False)
        return self.update_tiktok_channel(tiktok_id, hashtags_json=payload)

    def set_tiktok_schedule(self, tiktok_id: int, schedule: list) -> bool:
        payload = json.dumps(list(schedule or []), ensure_ascii=False)
        return self.update_tiktok_channel(tiktok_id, schedule_json=payload)

    # ─────────────────────────────────────────────────────────────────
    # СВЯЗИ TikTok ↔ YouTube
    # ─────────────────────────────────────────────────────────────────

    def ensure_tiktok_link(self, channel_id: int,
                           tiktok_handle: str | None) -> int | None:
        """Гарантирует запись TikTok-канала и связь с YouTube-каналом.

        Нормализует handle, при необходимости создаёт запись в
        tiktok_channels и заводит связь в tiktok_youtube_link.
        Возвращает id TikTok-канала либо None (пустой handle).
        """
        if not tiktok_handle:
            return None
        handle = str(tiktok_handle).strip().lstrip("@")
        if not handle:
            return None
        try:
            row = self.conn.execute(
                "SELECT id FROM tiktok_channels WHERE handle = ?", (handle,)
            ).fetchone()
            if row:
                tt_id = int(row["id"])
            else:
                cur = self.conn.cursor()
                cur.execute(
                    "INSERT INTO tiktok_channels (handle, display_name) "
                    "VALUES (?, ?)", (handle, handle)
                )
                tt_id = int(cur.lastrowid)
            self.conn.execute(
                "INSERT OR IGNORE INTO tiktok_youtube_link "
                "(tiktok_id, youtube_id) VALUES (?, ?)",
                (int(tt_id), int(channel_id))
            )
            self._commit()
            return tt_id
        except Exception as e:
            try:
                import logging
                logging.getLogger(__name__).exception(
                    "ensure_tiktok_link failed: %s", e
                )
            except Exception:
                pass
            return None

    def link_tiktok_to_youtube(self, tiktok_id: int, youtube_id: int) -> bool:
        try:
            self.conn.execute(
                "INSERT OR IGNORE INTO tiktok_youtube_link (tiktok_id, youtube_id) VALUES (?, ?)",
                (int(tiktok_id), int(youtube_id))
            )
            self._commit()
            return True
        except Exception:
            return False

    def unlink_tiktok_youtube(self, tiktok_id: int, youtube_id: int) -> bool:
        self.conn.execute(
            "DELETE FROM tiktok_youtube_link WHERE tiktok_id = ? AND youtube_id = ?",
            (int(tiktok_id), int(youtube_id))
        )
        self._commit()
        return True

    def list_youtube_for_tiktok(self, tiktok_id: int) -> list:
        rows = self.conn.execute("""
            SELECT c.*
            FROM channels c
            JOIN tiktok_youtube_link l ON c.id = l.youtube_id
            WHERE l.tiktok_id = ?
            ORDER BY c.added_at DESC
        """, (int(tiktok_id),)).fetchall()
        return [dict(r) for r in rows]

    def list_tiktok_for_youtube(self, youtube_id: int) -> list:
        rows = self.conn.execute("""
            SELECT t.*
            FROM tiktok_channels t
            JOIN tiktok_youtube_link l ON t.id = l.tiktok_id
            WHERE l.youtube_id = ?
            ORDER BY t.created_at DESC
        """, (int(youtube_id),)).fetchall()
        return [dict(r) for r in rows]

    # ─────────────────────────────────────────────────────────────────
    # КЛИПЫ
    # ─────────────────────────────────────────────────────────────────

    def add_clip(self, tiktok_id: int, file_path: str,
                 source_video_id: int = None,
                 duration: float = None,
                 status: str = "ready") -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO clips (tiktok_id, source_video_id, file_path, duration, status)
            VALUES (?, ?, ?, ?, ?)
        """, (int(tiktok_id), source_video_id, file_path, duration, status))
        self._commit()
        return cur.lastrowid

    def list_clips(self, tiktok_id: int, status: str = None) -> list:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM clips WHERE tiktok_id = ? AND status = ? "
                "ORDER BY generated_at DESC",
                (int(tiktok_id), status)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM clips WHERE tiktok_id = ? "
                "ORDER BY generated_at DESC",
                (int(tiktok_id),)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_clip(self, clip_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM clips WHERE id = ?", (int(clip_id),)
        ).fetchone()
        return dict(row) if row else None

    def mark_clip_published(self, clip_id: int):
        self.conn.execute(
            "UPDATE clips SET status = 'published', published_at = ? WHERE id = ?",
            (datetime.now().isoformat(), int(clip_id))
        )
        self._commit()

    def count_ready_clips(self, tiktok_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM clips WHERE tiktok_id = ? AND status = 'ready'",
            (int(tiktok_id),)
        ).fetchone()
        return row["n"] if row else 0

    def delete_clip(self, clip_id: int):
        self.conn.execute("DELETE FROM clips WHERE id = ?", (int(clip_id),))
        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # СКРИПТЫ ПУБЛИКАЦИИ
    # ─────────────────────────────────────────────────────────────────

    def add_publish_script(self, tiktok_id: int, clip_id: int = None,
                           title: str = None, file_path: str = None,
                           hashtags: str = None, caption: str = None,
                           scheduled_at: str = None,
                           status: str = "draft") -> int:
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO publish_scripts
                (tiktok_id, clip_id, title, file_path, hashtags,
                 scheduled_at, caption, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (int(tiktok_id), clip_id, title, file_path, hashtags,
              scheduled_at, caption, status))
        self._commit()
        return cur.lastrowid

    def list_publish_scripts(self, tiktok_id: int, status: str = None) -> list:
        if status:
            rows = self.conn.execute(
                "SELECT * FROM publish_scripts WHERE tiktok_id = ? AND status = ? "
                "ORDER BY created_at DESC",
                (int(tiktok_id), status)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM publish_scripts WHERE tiktok_id = ? "
                "ORDER BY created_at DESC",
                (int(tiktok_id),)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_publish_script(self, script_id: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM publish_scripts WHERE id = ?", (int(script_id),)
        ).fetchone()
        return dict(row) if row else None

    def update_publish_script_status(self, script_id: int, status: str) -> bool:
        if status == "done":
            self.conn.execute(
                "UPDATE publish_scripts SET status = ?, scheduled_at = COALESCE(scheduled_at, ?) "
                "WHERE id = ?",
                (status, datetime.now().isoformat(), int(script_id))
            )
            # Если скрипт закрыт — помечаем клип как опубликованный
            row = self.conn.execute(
                "SELECT clip_id FROM publish_scripts WHERE id = ?", (int(script_id),)
            ).fetchone()
            if row and row["clip_id"]:
                self.mark_clip_published(row["clip_id"])
        else:
            self.conn.execute(
                "UPDATE publish_scripts SET status = ? WHERE id = ?",
                (status, int(script_id))
            )
        self._commit()
        return True

    def delete_publish_script(self, script_id: int):
        self.conn.execute("DELETE FROM publish_scripts WHERE id = ?", (int(script_id),))
        self._commit()

    # ─────────────────────────────────────────────────────────────────
    # НАСТРОЙКИ АВТОМАТИЗАЦИИ
    # ─────────────────────────────────────────────────────────────────

    _AUTO_DEFAULTS = {
        "download_enabled": 1,
        "min_duration_sec": 300,
        "max_duration_sec": 1800,
        "max_age_days": 7,
        "fallback_popular": 1,
        "processing_enabled": 1,
        "banner_dir": None,
        "retention_dir": None,
        "background_dir": None,
        "clip_duration_sec": 30,
        "publish_enabled": 1,
        "auto_active": 0,
    }

    def _default_media_dirs(self) -> dict:
        """Возвращает дефолтные пути для banner/retention/background.
        Используется при INSERT в automation_settings и как фолбэк
        при пустых значениях, чтобы пайплайн всегда находил файлы.
        """
        try:
            from utils import (
                get_project_base, DIR_BANNERS, DIR_RETENTION, DIR_BACKGROUNDS,
            )
        except Exception:
            base = os.path.dirname(os.path.abspath(__file__))
            return {
                "banner_dir":     os.path.join(base, "баннер"),
                "retention_dir":  os.path.join(base, "удержание"),
                "background_dir": os.path.join(base, "фон"),
            }
        base = get_project_base()
        return {
            "banner_dir":     os.path.join(base, DIR_BANNERS),
            "retention_dir":  os.path.join(base, DIR_RETENTION),
            "background_dir": os.path.join(base, DIR_BACKGROUNDS),
        }

    def get_automation_settings(self, channel_id: int) -> dict:
        """Возвращает настройки автоматизации для YouTube-канала;
        создаёт дефолтные если нет.

        Если папки banner/retention/background пусты или NULL — в
        возвращаемом dict подставляются дефолты (<BASE>/баннер/, и т.п.),
        чтобы вызывающий код мог их использовать как фолбэк. В БД при
        этом ничего не пишется — пользователь видит «пустое поле +
        плейсхолдер» в UI.
        """
        row = self.conn.execute(
            "SELECT * FROM automation_settings WHERE channel_id = ?",
            (int(channel_id),)
        ).fetchone()
        if not row:
            defaults = self._default_media_dirs()
            self.conn.execute(
                "INSERT INTO automation_settings "
                "(channel_id, banner_dir, retention_dir, background_dir) "
                "VALUES (?, ?, ?, ?)",
                (int(channel_id),
                 defaults["banner_dir"],
                 defaults["retention_dir"],
                 defaults["background_dir"])
            )
            self._commit()
            row = self.conn.execute(
                "SELECT * FROM automation_settings WHERE channel_id = ?",
                (int(channel_id),)
            ).fetchone()

        d = dict(row)
        defaults = self._default_media_dirs()
        for key in ("banner_dir", "retention_dir", "background_dir"):
            if not d.get(key):
                d[key] = defaults[key]
        return d

    def set_automation_settings(self, channel_id: int, **fields) -> bool:
        allowed = set(self._AUTO_DEFAULTS.keys())
        data = {k: v for k, v in fields.items() if k in allowed}
        if not data:
            return False
        self.get_automation_settings(int(channel_id))  # гарантируем запись
        data["updated_at"] = datetime.now().isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in data)
        values = list(data.values()) + [int(channel_id)]
        self.conn.execute(
            f"UPDATE automation_settings SET {set_clause} WHERE channel_id = ?",
            values
        )
        self._commit()
        return True

    def set_auto_active(self, channel_id: int, active: bool) -> bool:
        """Включает/выключает автоматизацию для конкретного канала."""
        self.get_automation_settings(int(channel_id))
        self.conn.execute(
            "UPDATE automation_settings "
            "SET auto_active = ?, updated_at = ? WHERE channel_id = ?",
            (1 if active else 0, datetime.now().isoformat(), int(channel_id))
        )
        self._commit()
        return True

    def list_active_automation_channels(self) -> list[int]:
        """Возвращает id каналов, у которых включена автоматизация."""
        rows = self.conn.execute(
            "SELECT channel_id FROM automation_settings WHERE auto_active = 1"
        ).fetchall()
        return [int(r[0]) for r in rows]

    def get_tiktok_for_channel(self, channel_id: int) -> list:
        """Возвращает список id TikTok-каналов, привязанных к YouTube-каналу."""
        rows = self.conn.execute(
            "SELECT tiktok_id FROM tiktok_youtube_link WHERE youtube_id = ?",
            (int(channel_id),)
        ).fetchall()
        return [int(r[0]) for r in rows]

    # ─────────────────────────────────────────────────────────────────
    # НАСТРОЙКИ ПРИЛОЖЕНИЯ (key/value)
    # ─────────────────────────────────────────────────────────────────

    def get_setting(self, key: str, default=None):
        row = self.conn.execute(
            "SELECT value FROM app_settings WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return default
        raw = row["value"]
        if raw is None:
            return default
        # Попробуем распарсить JSON (для dict/list), иначе строка
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def set_setting(self, key: str, value) -> bool:
        if isinstance(value, (dict, list, tuple)):
            payload = json.dumps(value, ensure_ascii=False)
        elif value is None:
            payload = None
        else:
            payload = str(value)
        self.conn.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
        """, (key, payload))
        self._commit()
        return True

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

def _create_db_instance() -> "Database":
    import sys, tempfile
    # Пробуем основной путь
    try:
        _d = os.path.dirname(DB_PATH)
        os.makedirs(_d, exist_ok=True)
        # Проверяем что можем реально создать файл
        _test = os.path.join(_d, ".write_test")
        with open(_test, "w") as _f:
            _f.write("ok")
        os.remove(_test)
        return Database(DB_PATH)
    except Exception as e1:
        print(f"[db] Основной путь недоступен: {DB_PATH}\n  Причина: {e1}", file=sys.stderr)

    # Fallback: папка TEMP
    try:
        _tmp_dir = os.path.join(tempfile.gettempdir(), "yt_manager_data")
        os.makedirs(_tmp_dir, exist_ok=True)
        _fallback = os.path.join(_tmp_dir, "app.db")
        print(f"[db] Использую резервный путь: {_fallback}", file=sys.stderr)
        return Database(_fallback)
    except Exception as e2:
        raise RuntimeError(
            f"Не удалось открыть базу данных.\n\n"
            f"Основной путь: {DB_PATH}\n"
            f"Ошибка: {e1}\n\n"
            f"Резервный путь: {_fallback}\n"
            f"Ошибка: {e2}\n\n"
            f"Проверь:\n"
            f"  • Права на запись в папку проекта\n"
            f"  • Длину пути (Windows: не более 200 символов)\n"
            f"  • Не открыт ли файл app.db в другой программе"
        ) from e2


db = _create_db_instance()
