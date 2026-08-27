from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal


class RenderWorker(QThread):
    progress_changed = Signal(int, str)
    result_ready = Signal(str, bool)
    error_occurred = Signal(str)

    def __init__(
        self,
        *,
        audio_path: Path,
        subtitle_path: Path | None,
        image_path: Path | None,
        output_path: Path,
        width: int,
        height: int,
        fps: int = 30,
        crf: int = 23,
        image_mode: str = "fit",
        subtitle_font: str = "Tahoma",
        subtitle_size: int = 38,
        subtitle_margin: int = 150,
        preview_seconds: int | None = None,
        parent=None,
    ):
        super().__init__(parent)

        self.audio_path = Path(audio_path)
        self.subtitle_path = (
            Path(subtitle_path)
            if subtitle_path is not None
            else None
        )
        self.image_path = (
            Path(image_path)
            if image_path is not None
            else None
        )
        self.output_path = Path(output_path)

        self.width = max(320, int(width))
        self.height = max(320, int(height))
        self.fps = max(1, int(fps))
        self.crf = min(40, max(0, int(crf)))

        self.image_mode = image_mode
        self.subtitle_font = subtitle_font.strip() or "Tahoma"
        self.subtitle_size = max(12, int(subtitle_size))
        self.subtitle_margin = max(0, int(subtitle_margin))

        self.preview_seconds = (
            max(1, int(preview_seconds))
            if preview_seconds is not None
            else None
        )

        self._process: subprocess.Popen | None = None
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True

        process = self._process

        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def run(self):
        try:
            self.render()
        except Exception as error:
            if self._cancel_requested:
                self.error_occurred.emit("عملیات ساخت ویدئو لغو شد.")
            else:
                self.error_occurred.emit(
                    f"{type(error).__name__}: {error}"
                )

    def render(self):
        ffmpeg_path = shutil.which("ffmpeg")
        ffprobe_path = shutil.which("ffprobe")

        if not ffmpeg_path:
            raise RuntimeError(
                "FFmpeg در PATH ویندوز پیدا نشد."
            )

        if not ffprobe_path:
            raise RuntimeError(
                "ffprobe در PATH ویندوز پیدا نشد."
            )

        if not self.audio_path.exists():
            raise FileNotFoundError(
                f"فایل صوتی پیدا نشد:\n{self.audio_path}"
            )

        if (
            self.image_path is not None
            and not self.image_path.exists()
        ):
            raise FileNotFoundError(
                f"فایل تصویر پیدا نشد:\n{self.image_path}"
            )

        duration = self.probe_duration(
            ffprobe_path,
            self.audio_path,
        )

        is_preview = self.preview_seconds is not None

        if self.preview_seconds is not None:
            duration = min(
                duration,
                float(self.preview_seconds),
            )

        if duration <= 0:
            raise RuntimeError(
                "مدت فایل صوتی قابل تشخیص نیست."
            )

        self.output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            if self.output_path.exists():
                self.output_path.unlink()
        except OSError:
            pass

        command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
        ]

        filters: list[str] = []

        if self.image_path is not None:
            command.extend([
                "-loop",
                "1",
                "-framerate",
                str(self.fps),
                "-i",
                str(self.image_path),
            ])

            filters.append(self.create_image_filter())
        else:
            command.extend([
                "-f",
                "lavfi",
                "-i",
                (
                    f"color=c=0x101820:"
                    f"s={self.width}x{self.height}:"
                    f"r={self.fps}"
                ),
            ])

            filters.append("format=yuv420p")

        command.extend([
            "-i",
            str(self.audio_path),
        ])

        if (
            self.subtitle_path is not None
            and self.subtitle_path.exists()
        ):
            filters.append(self.create_subtitle_filter())

        command.extend([
            "-vf",
            ",".join(filters),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.6f}",
            "-r",
            str(self.fps),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(self.crf),
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(self.output_path),
        ])

        creation_flags = 0

        if os.name == "nt":
            creation_flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        self.progress_changed.emit(
            1,
            "آماده‌سازی FFmpeg...",
        )

        self._process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creation_flags,
            bufsize=1,
        )

        recent_lines: list[str] = []

        if self._process.stdout is not None:
            for raw_line in self._process.stdout:
                line = raw_line.strip()

                if line:
                    recent_lines.append(line)
                    recent_lines = recent_lines[-35:]

                if self._cancel_requested:
                    self.cancel()
                    break

                progress = self.extract_progress(
                    line,
                    duration,
                )

                if progress is not None:
                    self.progress_changed.emit(
                        progress,
                        f"در حال ساخت ویدئو: {progress}٪",
                    )

        return_code = self._process.wait()
        self._process = None

        if self._cancel_requested:
            try:
                if self.output_path.exists():
                    self.output_path.unlink()
            except OSError:
                pass

            raise RuntimeError(
                "عملیات توسط کاربر لغو شد."
            )

        if return_code != 0:
            details = "\n".join(recent_lines)

            raise RuntimeError(
                "FFmpeg نتوانست ویدئو را تولید کند.\n\n"
                f"کد خروج: {return_code}\n\n"
                f"{details}"
            )

        if not self.output_path.exists():
            raise RuntimeError(
                "فرآیند FFmpeg تمام شد اما فایل خروجی ساخته نشد."
            )

        self.progress_changed.emit(
            100,
            "ساخت ویدئو با موفقیت کامل شد.",
        )

        self.result_ready.emit(
            str(self.output_path),
            is_preview,
        )

    def create_image_filter(self) -> str:
        width = self.width
        height = self.height

        if self.image_mode == "fill":
            return (
                f"scale={width}:{height}:"
                "force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                "setsar=1,"
                "format=yuv420p"
            )

        if self.image_mode == "stretch":
            return (
                f"scale={width}:{height},"
                "setsar=1,"
                "format=yuv420p"
            )

        return (
            f"scale={width}:{height}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:"
            "(ow-iw)/2:(oh-ih)/2:"
            "color=0x101820,"
            "setsar=1,"
            "format=yuv420p"
        )

    def create_subtitle_filter(self) -> str:
        assert self.subtitle_path is not None

        escaped_path = (
            self.subtitle_path
            .resolve()
            .as_posix()
            .replace("\\", "/")
            .replace(":", r"\:")
            .replace("'", r"\'")
        )

        font = (
            self.subtitle_font
            .replace("\\", r"\\")
            .replace("'", r"\'")
            .replace(",", r"\,")
        )

        style = (
            f"FontName={font},"
            f"FontSize={self.subtitle_size},"
            "PrimaryColour=&H00FFFFFF,"
            "OutlineColour=&H00000000,"
            "BackColour=&H80000000,"
            "BorderStyle=1,"
            "Outline=3,"
            "Shadow=1,"
            "Alignment=2,"
            f"MarginV={self.subtitle_margin}"
        )

        return (
            f"subtitles=filename='{escaped_path}':"
            "charenc=UTF-8:"
            f"force_style='{style}'"
        )

    @staticmethod
    def probe_duration(
        ffprobe_path: str,
        audio_path: Path,
    ) -> float:
        creation_flags = 0

        if os.name == "nt":
            creation_flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        result = subprocess.run(
            [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=True,
            creationflags=creation_flags,
        )

        return float(result.stdout.strip())

    @staticmethod
    def extract_progress(
        line: str,
        duration: float,
    ) -> int | None:
        if duration <= 0:
            return None

        if line.startswith("out_time_us="):
            value = line.split("=", 1)[1].strip()

            try:
                microseconds = int(value)
            except ValueError:
                return None

            percent = round(
                microseconds /
                (duration * 1_000_000) *
                100
            )

            return min(99, max(1, percent))

        if line.startswith("out_time_ms="):
            value = line.split("=", 1)[1].strip()

            try:
                microseconds = int(value)
            except ValueError:
                return None

            percent = round(
                microseconds /
                (duration * 1_000_000) *
                100
            )

            return min(99, max(1, percent))

        if line.startswith("out_time="):
            value = line.split("=", 1)[1].strip()
            match = re.match(
                r"(\d+):(\d+):(\d+(?:\.\d+)?)",
                value,
            )

            if not match:
                return None

            hours = int(match.group(1))
            minutes = int(match.group(2))
            seconds = float(match.group(3))

            elapsed = (
                hours * 3600 +
                minutes * 60 +
                seconds
            )

            percent = round(
                elapsed / duration * 100
            )

            return min(99, max(1, percent))

        return None
