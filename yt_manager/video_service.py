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
    stderr дренируется в отдельном потоке чтобы избежать deadlock.
    """
    import subprocess
    import threading

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

        stderr_lines = []

        def _drain_stderr():
            for raw in iter(process.stderr.readline, b''):
                line = raw.decode('utf-8', errors='ignore').rstrip()
                if line:
                    stderr_lines.append(line)
            process.stderr.close()

        # Дренируем stderr в отдельном потоке — без этого ffmpeg deadlock-ается
        t = threading.Thread(target=_drain_stderr, daemon=True)
        t.start()

        for raw in iter(process.stdout.readline, b''):
            line = raw.decode('utf-8', errors='ignore').strip()
            if line.startswith('out_time_ms='):
                try:
                    ms = int(line.split('=')[1])
                    if ms > 0 and total_duration > 0:
                        pct = min(99, int(ms / (total_duration * 1_000_000) * 100))
                        progress_cb(pct, f'Обработка {pct}%...')
                except (ValueError, ZeroDivisionError):
                    pass

        process.stdout.close()
        t.join(timeout=30)
        process.wait()

        if process.returncode not in (0, None):
            err = ' '.join(stderr_lines[-5:])
            raise RuntimeError(f'{desc} exit {process.returncode}: {err[-300:]}')

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
        clip_duration: int   = 60,
        clip_count:    int   = 0,   # если > 0 — нарезать на N равных частей
        prefix:        str   = 'clip',
        reencode:      bool  = False,
        progress_cb:   Optional[Callable] = None,
    ) -> CutResult:
        """
        Нарезает видео на клипы.
        - clip_duration: длина каждого клипа в секундах
        - clip_count>0:  нарезать на N равных частей (clip_duration игнорируется)
        """
        os.makedirs(output_dir, exist_ok=True)
        info  = self.get_video_info(input_path)
        total = info.duration

        if clip_count and clip_count > 0:
            clip_duration = max(1, int(total / clip_count))
            n_clips       = clip_count
        else:
            n_clips = max(1, int(total // clip_duration)
                          + (1 if total % clip_duration > 1 else 0))
        result = CutResult(total=n_clips)

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
                        preset='ultrafast', crf=23,
                        threads=0,
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
        bg_path:        str            = None,
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
        Композиция видео через overlay (без обрезки и изменения пропорций).

        Логика:
          1. ФОН (bg_path) масштабируется/обрезается на весь output_width x output_height
          2. ГЛАВНЫЙ РОЛИК (center_path) накладывается по центру БЕЗ изменения размеров
          3. БАННЕР (top_path) стыкуется вплотную сверху к главному БЕЗ изменений
          4. УДЕРЖАНИЕ (bottom_path) стыкуется вплотную снизу к главному БЕЗ изменений
        """
        import subprocess, threading

        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

        center_info = self.get_video_info(center_path)
        duration    = center_info.duration
        cw          = center_info.width  or output_width
        ch          = center_info.height or output_height

        quality_map = {'fast': 'ultrafast', 'medium': 'fast', 'slow': 'medium', 'good': 'fast', 'best': 'slow'}
        preset = quality_map.get(quality, 'ultrafast')

        def esc(p):
            return p.replace('\\', '/').replace(':', '\\:').replace("'", "\\'")

        # ── Индексы входов ──────────────────────────────────────────
        inputs      = []
        filter_parts = []
        idx          = 0

        inputs += ['-i', center_path]
        center_idx = idx; idx += 1

        has_top = bool(top_path and os.path.isfile(top_path))
        has_bot = bool(bottom_path and os.path.isfile(bottom_path))
        has_bg  = bool(bg_path and os.path.isfile(bg_path))

        if has_top:
            inputs += ['-stream_loop', '-1', '-t', str(duration), '-i', top_path]
            top_idx = idx; idx += 1
        else:
            top_idx = None

        if has_bot:
            inputs += ['-stream_loop', '-1', '-t', str(duration), '-i', bottom_path]
            bot_idx = idx; idx += 1
        else:
            bot_idx = None

        if has_bg:
            inputs += ['-stream_loop', '-1', '-t', str(duration), '-i', bg_path]
            bg_idx = idx; idx += 1
        else:
            bg_idx = None

        # ── Получаем реальные размеры top/bottom БЕЗ изменений ─────
        # Размеры top и bottom берём из самих файлов (не трогаем)
        top_w, top_h_real = 0, 0
        bot_w, bot_h_real = 0, 0
        if has_top:
            try:
                ti = self.get_video_info(top_path)
                top_w, top_h_real = ti.width or 0, ti.height or 0
            except Exception:
                pass
        if has_bot:
            try:
                bi = self.get_video_info(bottom_path)
                bot_w, bot_h_real = bi.width or 0, bi.height or 0
            except Exception:
                pass

        # ── Масштабируем главное видео: ширина = output_width, высота по пропорциям ──
        # Боковых полос нет — видео от края до края по ширине
        if cw > 0 and ch > 0:
            scale  = output_width / cw
            new_cw = output_width
            new_ch = int(ch * scale)
            if new_ch % 2 != 0: new_ch -= 1
        else:
            new_cw, new_ch = output_width, output_height

        # ── Вычисляем позиции overlay ───────────────────────────────
        # Весь стек центрируем вертикально на фоне
        total_stack_h = top_h_real + new_ch + bot_h_real
        stack_top_y   = max(0, (output_height - total_stack_h) // 2)

        center_x = max(0, (output_width - new_cw) // 2)
        center_y = stack_top_y + top_h_real

        # Баннер: прямо над главным, центрируем по горизонтали
        top_x = max(0, (output_width - top_w) // 2) if top_w else 0
        top_y = center_y - top_h_real

        # Удержание: прямо под главным, центрируем по горизонтали
        bot_x = max(0, (output_width - bot_w) // 2) if bot_w else 0
        bot_y = center_y + new_ch

        # ── Строим filtergraph ──────────────────────────────────────
        # Шаг 1: Фон на весь экран (scale+crop — только фон обрезается)
        if has_bg:
            filter_parts.append(
                f"[{bg_idx}:v]scale={output_width}:{output_height}:"
                f"force_original_aspect_ratio=increase,"
                f"crop={output_width}:{output_height},setsar=1[bg]"
            )
            base_label = 'bg'
        else:
            filter_parts.append(
                f"color=c={bg_color}:size={output_width}x{output_height}:"
                f"rate=30:d={duration}[bg]"
            )
            base_label = 'bg'

        # Шаг 2: Главное видео — масштабируем чтобы вписалось, накладываем по центру
        filter_parts.append(
            f"[{center_idx}:v]scale={new_cw}:{new_ch},setsar=1[ctr]"
        )
        filter_parts.append(
            f"[{base_label}][ctr]overlay={center_x}:{center_y}[v1]"
        )
        cur_label = 'v1'

        # Шаг 3: Баннер — без изменений, overlay прямо над главным
        if has_top and top_h_real > 0:
            filter_parts.append(f"[{top_idx}:v]setsar=1[top_v]")
            filter_parts.append(
                f"[{cur_label}][top_v]overlay={top_x}:{max(0,top_y)}[v2]"
            )
            cur_label = 'v2'

        # Шаг 4: Удержание — без изменений, overlay прямо под главным
        if has_bot and bot_h_real > 0:
            filter_parts.append(f"[{bot_idx}:v]setsar=1[bot_v]")
            filter_parts.append(
                f"[{cur_label}][bot_v]overlay={bot_x}:{bot_y}[v3]"
            )
            cur_label = 'v3'

        final_v = f'[{cur_label}]'
        filtergraph = ';'.join(filter_parts)

        # ── Аудио источник ─────────────────────────────────────────
        audio_map = {
            'center': center_idx,
            'top':    top_idx,
            'bottom': bot_idx,
        }
        aidx = audio_map.get(audio_source, center_idx) or center_idx

        # ── Автовыбор кодировщика ──────────────────────────────────
        def _detect_encoder():
            try:
                import subprocess as _sp
                r = _sp.run(['ffmpeg', '-encoders'], capture_output=True, text=True, timeout=8)
                enc_list = r.stdout + r.stderr
                if 'h264_nvenc' in enc_list:
                    return 'nvenc'
                if 'h264_qsv' in enc_list:
                    return 'qsv'
            except Exception:
                pass
            return 'cpu'

        hw = _detect_encoder()
        log.debug('stack_videos encoder: %s', hw)

        if hw == 'nvenc':
            vcodec_args = ['-vcodec', 'h264_nvenc', '-preset', 'p4',
                           '-rc', 'vbr', '-cq', '26', '-b:v', '0', '-spatial_aq', '1']
        elif hw == 'qsv':
            vcodec_args = ['-vcodec', 'h264_qsv', '-global_quality', '26', '-preset', 'faster']
        else:
            vcodec_args = ['-vcodec', 'libx264', '-preset', preset, '-crf', '26', '-threads', '0']

        # ── Финальная команда ──────────────────────────────────────
        cmd = ['ffmpeg', '-y'] + inputs + [
            '-filter_complex', filtergraph,
            '-map', final_v,
            '-map', f'{aidx}:a',
        ] + vcodec_args + [
            '-acodec', 'aac',
            '-ar', '44100',
            '-t', str(duration),
            '-progress', 'pipe:1',
            '-nostats',
            output_path,
        ]

        log.debug('stack_videos cmd: %s', ' '.join(cmd))

        if progress_cb:
            progress_cb(5, 'Запуск рендеринга...')

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        stderr_lines = []
        def _drain():
            for raw in iter(process.stderr.readline, b''):
                line = raw.decode('utf-8', errors='ignore').rstrip()
                if line: stderr_lines.append(line)
            process.stderr.close()

        import threading
        t = threading.Thread(target=_drain, daemon=True)
        t.start()

        for raw in iter(process.stdout.readline, b''):
            line = raw.decode('utf-8', errors='ignore').strip()
            if line.startswith('out_time_ms='):
                try:
                    ms  = int(line.split('=')[1])
                    pct = min(99, int(ms / 1000 / duration * 95) + 5)
                    if progress_cb:
                        progress_cb(pct, f'Рендеринг... {pct}%')
                except Exception:
                    pass

        process.stdout.close()
        process.wait()
        t.join(timeout=5)

        if process.returncode not in (0, None):
            err = '\n'.join(stderr_lines[-10:])
            raise RuntimeError(f'stack_videos failed (exit {process.returncode}):\n{err}')

        if progress_cb:
            progress_cb(100, 'Готово!')
        return output_path

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
            elif op == 'stack_and_cut':
                # Шаг 1: Стекинг
                stack_kw = {k: v for k, v in self.kwargs.items()
                            if k not in ('cut_duration', 'cut_prefix', 'cut_reencode', 'cut_output_dir', 'cut_count', 'cut_by_count')}
                def _cb_stack(p, m):
                    self.progress.emit(p // 2, m or 'Рендеринг...')
                path = self._service.stack_videos(progress_cb=_cb_stack, **stack_kw)
                # Шаг 2: Нарезка результата
                cut_dur    = self.kwargs.get('cut_duration', 60)
                cut_cnt    = self.kwargs.get('cut_count', 0)
                cut_prefix = self.kwargs.get('cut_prefix', 'clip')
                cut_re     = self.kwargs.get('cut_reencode', False)
                cut_dir    = self.kwargs.get('cut_output_dir', os.path.dirname(path))
                def _cb_cut(p, m):
                    self.progress.emit(50 + p // 2, m or 'Нарезка...')
                result = self._service.cut_video(
                    input_path=path,
                    output_dir=cut_dir,
                    clip_duration=cut_dur,
                    clip_count=cut_cnt,
                    prefix=cut_prefix,
                    reencode=cut_re,
                    progress_cb=_cb_cut,
                )
                self.finished.emit([path] + result.clips)
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
