# video_service.py — Обработка видео через ffmpeg
#
# VideoService   — нарезка, склейка, стекинг
# ProcessWorker  — QThread-обёртка с прогрессом
# video_service  — глобальный инстанс

import os
import re
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Optional, Callable

import ffmpeg
from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# ДАТАКЛАССЫ
# ──────────────────────────────────────────────────────────────────────

@dataclass
class VideoFileInfo:
    """Метаинформация о локальном видеофайле."""
    path:      str
    duration:  float = 0.0
    width:     int   = 0
    height:    int   = 0
    fps:       float = 0.0
    codec:     str   = ""
    size_mb:   float = 0.0

    @property
    def resolution(self) -> str:
        return f'{self.width}x{self.height}' if self.width else '—'

    @property
    def duration_str(self) -> str:
        h, rem = divmod(int(self.duration), 3600)
        m, s   = divmod(rem, 60)
        return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


@dataclass
class CutResult:
    """Результат нарезки: пути к клипам и статистика."""
    clips:     list = field(default_factory=list)
    total:     int  = 0
    succeeded: int  = 0
    failed:    int  = 0


# ──────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────────────────────────────

def is_ffmpeg_available() -> bool:
    """Проверяет наличие ffmpeg в системе."""
    try:
        subprocess.run(["ffmpeg", "-version"],
                       capture_output=True, check=True, timeout=5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError,
            subprocess.TimeoutExpired):
        return False


def sanitize_filename(name: str) -> str:
    """Очищает имя файла от запрещённых символов."""
    return re.sub(r'[/:*?<>|\\]', '_', name).strip()[:120]


def _probe(path: str) -> dict:
    try:
        return ffmpeg.probe(path)
    except ffmpeg.Error as e:
        stderr = e.stderr.decode(errors='ignore') if e.stderr else ''
        raise RuntimeError(f'ffprobe failed: {path} | {stderr}') from e


def _pick_video_stream(probe: dict) -> Optional[dict]:
    for s in probe.get('streams', []):
        if s.get('codec_type') == 'video':
            return s
    return None


def _parse_fps(fps_str: str) -> float:
    try:
        if '/' in fps_str:
            num, den = fps_str.split('/')
            return round(float(num) / float(den), 3)
        return float(fps_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


def _run_ffmpeg(stream, desc: str = 'ffmpeg'):
    """Запускает ffmpeg-поток; при ошибке бросает RuntimeError."""
    try:
        stream.overwrite_output().run(quiet=True, capture_stderr=True)
    except ffmpeg.Error as e:
        stderr = e.stderr.decode(errors='ignore') if e.stderr else ''
        log.error('%s error: %s', desc, stderr[-600:])
        raise RuntimeError(
            f'{desc} failed. Убедись что ffmpeg установлен и в PATH.\n{stderr[-250:]}'
        ) from e


def _run_with_progress(
    stream,
    total_duration: float,
    progress_cb: Optional[Callable],
    desc: str = 'ffmpeg',
):
    """
    Запускает ffmpeg с парсингом прогресса через stdout pipe.
    Если progress_cb=None — просто запускает без отслеживания прогресса.
    """
    if not progress_cb:
        _run_ffmpeg(stream, desc)
        return

    try:
        process = (
            stream
            .overwrite_output()
            .global_args('-progress', 'pipe:1', '-nostats')
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        while True:
            raw = process.stdout.readline()
            if not raw:
                break
            line = raw.decode('utf-8', errors='ignore').strip()
            if line.startswith('out_time_ms='):
                try:
                    ms  = int(line.split('=')[1])
                    pct = min(99, int(ms / (total_duration * 1_000_000) * 100))
                    progress_cb(pct, '')
                except (ValueError, ZeroDivisionError):
                    pass
        process.wait()
        if process.returncode not in (0, None):
            stderr = process.stderr.read().decode(errors='ignore')
            raise RuntimeError(
                f'{desc} exit {process.returncode}: {stderr[-250:]}'
            )
        progress_cb(100, 'Готово')
    except ffmpeg.Error as e:
        stderr = e.stderr.decode(errors='ignore') if e.stderr else ''
        raise RuntimeError(f'{desc} failed: {stderr[-250:]}') from e


# ──────────────────────────────────────────────────────────────────────
# VIDEO SERVICE
# ──────────────────────────────────────────────────────────────────────

class VideoService:
    """
    Сервис для видеообработки через ffmpeg.
    Не зависит от Qt — пригоден для тестов и CLI.
    Все методы бросают RuntimeError при ошибке ffmpeg.
    """

    # ── Метаинформация ────────────────────────────────────────────────

    def get_video_info(self, path: str) -> VideoFileInfo:
        """Возвращает метаинформацию о локальном файле."""
        probe    = _probe(path)
        vs       = _pick_video_stream(probe)
        fmt      = probe.get('format', {})
        duration = float((vs or {}).get('duration') or fmt.get('duration', 0))
        size_b   = int(fmt.get('size', 0))
        return VideoFileInfo(
            path     = path,
            duration = duration,
            width    = int((vs or {}).get('width',  0)),
            height   = int((vs or {}).get('height', 0)),
            fps      = _parse_fps((vs or {}).get('r_frame_rate', '0/1')),
            codec    = (vs or {}).get('codec_name', ''),
            size_mb  = round(size_b / 1_048_576, 2),
        )

    # ── Нарезка ───────────────────────────────────────────────────────

    def cut_video(
        self,
        input_path:    str,
        output_dir:    str,
        clip_duration: int,
        prefix:        str  = 'clip',
        reencode:      bool = False,
        progress_cb:   Optional[Callable] = None,
    ) -> CutResult:
        """
        Нарезает видео на клипы по clip_duration секунд.

        Args:
            input_path:    Путь к исходному файлу.
            output_dir:    Папка для клипов.
            clip_duration: Длительность каждого клипа (сек).
            prefix:        Префикс имён файлов (prefix_001.mp4, ...).
            reencode:      True — libx264/aac; False — stream copy (быстро).
            progress_cb:   Функция(percent: int, message: str).

        Returns:
            CutResult со списком путей к созданным клипам.
        """
        os.makedirs(output_dir, exist_ok=True)
        info    = self.get_video_info(input_path)
        total   = info.duration
        n_clips = max(1, int(total // clip_duration)
                      + (1 if total % clip_duration > 1 else 0))
        result  = CutResult(total=n_clips)

        for idx in range(n_clips):
            start     = idx * clip_duration
            remaining = total - start
            if remaining < 1:
                break
            duration = min(float(clip_duration), remaining)
            out_path = os.path.join(output_dir, f'{prefix}_{idx+1:03d}.mp4')

            if progress_cb:
                progress_cb(int(idx / n_clips * 100), f'Клип {idx+1}/{n_clips}')

            try:
                inp = ffmpeg.input(input_path, ss=start, t=duration)
                if reencode:
                    stream = ffmpeg.output(
                        inp.video, inp.audio, out_path,
                        vcodec='libx264', acodec='aac',
                        preset='fast', crf=22,
                    )
                else:
                    stream = ffmpeg.output(
                        inp.video, inp.audio, out_path,
                        c='copy',
                        avoid_negative_ts='make_zero',
                    )
                _run_ffmpeg(stream, f'cut {idx+1}')
                result.clips.append(out_path)
                result.succeeded += 1
            except RuntimeError as e:
                log.error('cut_video clip %d failed: %s', idx + 1, e)
                result.failed += 1

        if progress_cb:
            progress_cb(100, f'Нарезка: {result.succeeded} клипов')
        return result

    # ── Склейка ───────────────────────────────────────────────────────

    def merge_videos(
        self,
        input_paths: list,
        output_path: str,
        reencode:    bool = False,
        progress_cb: Optional[Callable] = None,
    ) -> str:
        """
        Склеивает список видеофайлов в один.

        Args:
            input_paths: Список путей в нужном порядке.
            output_path: Путь к результирующему файлу.
            reencode:    True — concat filter + libx264 (совместимее, медленнее);
                         False — concat demuxer + stream copy (быстро).
        """
        if not input_paths:
            raise ValueError('input_paths пустой')
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        if progress_cb:
            progress_cb(5, f'Склейка {len(input_paths)} файлов...')

        if reencode:
            inputs = [ffmpeg.input(p) for p in input_paths]
            parts  = []
            for inp in inputs:
                parts.extend([inp.video, inp.audio])
            total  = sum(self.get_video_info(p).duration for p in input_paths)
            stream = (
                ffmpeg.concat(*parts, v=1, a=1)
                .output(output_path,
                        vcodec='libx264', acodec='aac', preset='fast')
            )
            _run_with_progress(stream, total, progress_cb, 'merge')
        else:
            list_file = output_path + '.concat.txt'
            try:
                with open(list_file, 'w', encoding='utf-8') as fh:
                    for p in input_paths:
                        abs_p = os.path.abspath(p)
                        fh.write(f"file '{abs_p}'\n")
                stream = (
                    ffmpeg.input(list_file, format='concat', safe=0)
                    .output(output_path, c='copy')
                )
                _run_ffmpeg(stream, 'merge concat')
            finally:
                if os.path.exists(list_file):
                    os.remove(list_file)

        if progress_cb:
            progress_cb(100, 'Склейка завершена')
        return output_path

    # ── Стекинг ───────────────────────────────────────────────────────

    def stack_videos(
        self,
        center_path:    str,
        output_path:    str,
        top_path:       str            = None,
        bottom_path:    str            = None,
        output_width:   int            = 1080,
        output_height:  int            = 1920,
        top_h:          int            = 320,
        center_h:       int            = 1280,
        bottom_h:       int            = 320,
        audio_source:   str            = 'center',
        subtitle_path:  str            = None,
        subtitle_size:  int            = 32,
        subtitle_color: str            = 'white',
        bg_color:       str            = 'black',
        quality:        str            = 'fast',
        progress_cb:    Optional[Callable] = None,
    ) -> str:
        """
        Стекает видео вертикально: верх (баннер) + центр + низ (фон).

        Ключевые особенности:
        - _scale_pad вместо _scale_crop: пропорции сохраняются, нет обрезки/растяжки
        - Слоты top/bottom опциональны: если не указан путь, заполняется bg_color
        - Длительность результата = длительность center-видео
        - audio_source задаёт источник звука; остальные слоты немые
        - subtitle_path (SRT) — субтитры поверх центрального слоя (требует libass в ffmpeg)
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        # Длительность итогового видео = длительность center
        center_info = self.get_video_info(center_path)
        duration = center_info.duration
        w = output_width

        def _scale_pad(inp_stream, tw: int, th: int) -> object:
            """
            Масштабирует видео вписывая в слот (scale-to-fit),
            не обрезает и не растягивает — добавляет padding bg_color.
            Формула: scale to fit + pad to exact size.
            """
            scaled = inp_stream.filter(
                'scale', tw, th,
                force_original_aspect_ratio='decrease',
                flags='lanczos',
            )
            padded = scaled.filter(
                'pad', tw, th,
                x='(ow-iw)/2', y='(oh-ih)/2',
                color=bg_color,
            )
            # Гарантируем ровно tw×th
            return padded.filter('setsar', '1/1')

        def _black_input(bw: int, bh: int) -> object:
            """Заглушка: чёрный (или bg_color) прямоугольник нужного размера."""
            return ffmpeg.input(
                f'color={bg_color}:size={bw}x{bh}:rate=30',
                format='lavfi', t=duration,
            )

        # ── Входные потоки ──
        center_in = ffmpeg.input(center_path)
        top_in    = ffmpeg.input(top_path)    if top_path    else None
        bottom_in = ffmpeg.input(bottom_path) if bottom_path else None

        # ── Видеодорожки слотов ──
        use_top    = top_in    is not None and top_h    > 0
        use_bottom = bottom_in is not None and bottom_h > 0

        center_v = _scale_pad(center_in.video, w, center_h)

        if use_top:
            top_v = _scale_pad(top_in.video, w, top_h)
        else:
            top_v = _black_input(w, top_h).video if top_h > 0 else None

        if use_bottom:
            bottom_v = _scale_pad(bottom_in.video, w, bottom_h)
        else:
            bottom_v = _black_input(w, bottom_h).video if bottom_h > 0 else None

        # ── Субтитры поверх центра ──
        if subtitle_path and os.path.isfile(subtitle_path):
            sub_path_ffmpeg = subtitle_path.replace('\\', '/').replace('\\', '/')
            center_v = center_v.filter(
                'subtitles', sub_path_ffmpeg,
                force_style=(
                    f'Fontsize={subtitle_size},'
                    f'PrimaryColour=&H00{subtitle_color},'
                    f'OutlineColour=&H000000,'
                    f'Outline=2,Shadow=1'
                ),
            )

        # ── Собираем стек ──
        parts = [v for v in [top_v, center_v, bottom_v] if v is not None]
        if len(parts) == 1:
            stacked = parts[0]
        else:
            stacked = ffmpeg.filter(parts, 'vstack', inputs=len(parts))

        # ── Аудио: только один источник, остальные немые ──
        audio_src_map = {
            'center': center_in if center_in else None,
            'top':    top_in    if use_top   else None,
            'bottom': bottom_in if use_bottom else None,
        }
        audio_node = audio_src_map.get(audio_source)
        if audio_node is None:
            audio_node = center_in  # fallback

        # ── Рендеринг ──
        preset_map = {'fast': 'fast', 'good': 'medium', 'best': 'slow'}
        enc_preset = preset_map.get(quality, 'fast')

        stream = ffmpeg.output(
            stacked, audio_node.audio, output_path,
            vcodec='libx264', acodec='aac',
            preset=enc_preset, crf=23,
            t=duration,                      # обрезаем по длительности center
        )

        if progress_cb:
            progress_cb(5, 'Запуск рендеринга...')

        _run_with_progress(stream, duration, progress_cb, 'stack')

        if progress_cb:
            progress_cb(100, 'Готово!')
        return output_path

    # ── Вырезка сегмента ──────────────────────────────────────────────

    def trim_video(
        self,
        input_path:  str,
        output_path: str,
        start_sec:   float,
        end_sec:     float,
        reencode:    bool = False,
        progress_cb: Optional[Callable] = None,
    ) -> str:
        """
        Вырезает конкретный временной отрезок из видео.

        Args:
            start_sec, end_sec: Границы сегмента в секундах.
            reencode: True — точнее по кадру; False — быстро (до ключевого кадра).
        """
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        duration = end_sec - start_sec
        if duration <= 0:
            raise ValueError('end_sec должен быть больше start_sec')

        inp = ffmpeg.input(input_path, ss=start_sec, t=duration)
        if reencode:
            stream = ffmpeg.output(
                inp.video, inp.audio, output_path,
                vcodec='libx264', acodec='aac', preset='fast', crf=22,
            )
        else:
            stream = ffmpeg.output(
                inp.video, inp.audio, output_path,
                c='copy', avoid_negative_ts='make_zero',
            )
        _run_with_progress(stream, duration, progress_cb, 'trim')
        return output_path


# ──────────────────────────────────────────────────────────────────────
# PROCESS WORKER — QThread для фоновой обработки
# ──────────────────────────────────────────────────────────────────────

class ProcessWorker(QThread):
    """
    Запускает задачу видеообработки в фоновом потоке.

    Поддерживаемые операции: 'cut' | 'merge' | 'stack' | 'trim'

    Пример использования:
        worker = ProcessWorker(
            'cut',
            input_path='/downloads/video.mp4',
            output_dir='/processed/clips',
            clip_duration=30
        )
        worker.progress.connect(lambda p, m: bar.setValue(p))
        worker.finished.connect(lambda paths: on_done(paths))
        worker.error.connect(lambda msg: show_error(msg))
        worker.start()
    """

    progress = pyqtSignal(int, str)   # percent (0-100), message
    finished = pyqtSignal(list)       # список путей к результатам
    error    = pyqtSignal(str)        # сообщение об ошибке

    def __init__(self, operation: str, parent=None, **kwargs):
        super().__init__(parent)
        self.operation = operation
        self.kwargs    = kwargs
        self._service  = VideoService()

    def run(self):
        cb = lambda p, m: self.progress.emit(p, m)
        try:
            op = self.operation
            if op == 'cut':
                result = self._service.cut_video(progress_cb=cb, **self.kwargs)
                self.finished.emit(result.clips)
            elif op == 'merge':
                path = self._service.merge_videos(progress_cb=cb, **self.kwargs)
                self.finished.emit([path])
            elif op == 'stack':
                path = self._service.stack_videos(progress_cb=cb, **self.kwargs)
                self.finished.emit([path])
            elif op == 'trim':
                path = self._service.trim_video(progress_cb=cb, **self.kwargs)
                self.finished.emit([path])
            else:
                self.error.emit(f'Неизвестная операция: {op}')
        except RuntimeError as e:
            log.error('ProcessWorker [%s]: %s', self.operation, e)
            self.error.emit(str(e))
        except Exception as e:
            log.exception('ProcessWorker [%s] unexpected: %s', self.operation, e)
            self.error.emit(f'Неожиданная ошибка: {e}')


# ──────────────────────────────────────────────────────────────────────
# ГЛОБАЛЬНЫЙ ИНСТАНС
# ──────────────────────────────────────────────────────────────────────

video_service = VideoService()
