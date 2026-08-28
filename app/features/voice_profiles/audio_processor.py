from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


class AudioProcessingError(RuntimeError):
    """خطای پردازش یا بررسی فایل صوتی."""


def _run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            ),
        )
    except FileNotFoundError as exc:
        raise AudioProcessingError(
            f"برنامه «{arguments[0]}» پیدا نشد."
        ) from exc


def inspect_audio(source_path: Path) -> dict[str, Any]:
    source_path = source_path.resolve()

    if not source_path.exists():
        raise AudioProcessingError(
            f"فایل صوتی پیدا نشد:\n{source_path}"
        )

    result = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source_path),
        ]
    )

    if result.returncode != 0:
        raise AudioProcessingError(
            "FFprobe نتوانست فایل صوتی را بررسی کند.\n\n"
            + (result.stderr.strip() or "خطای نامشخص")
        )

    try:
        payload = json.loads(result.stdout)
        streams = payload.get("streams") or []

        if not streams:
            raise ValueError("Audio stream not found")

        stream = streams[0]
        duration = float(
            (payload.get("format") or {}).get("duration", 0)
        )

        return {
            "duration": duration,
            "codec": stream.get("codec_name") or "unknown",
            "sample_rate": int(stream.get("sample_rate") or 0),
            "channels": int(stream.get("channels") or 0),
            "size_bytes": source_path.stat().st_size,
        }
    except (TypeError, ValueError, KeyError) as exc:
        raise AudioProcessingError(
            "اطلاعات فایل صوتی معتبر نیست."
        ) from exc


def process_voice_sample(
    source_path: Path,
    destination_path: Path,
) -> dict[str, Any]:
    source_path = source_path.resolve()
    destination_path = destination_path.resolve()

    inspect_audio(source_path)
    destination_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_path = destination_path.with_suffix(".processing.wav")
    temporary_path.unlink(missing_ok=True)

    # areverse باعث می‌شود سکوت انتهای فایل نیز بدون حذف
    # مکث‌های طبیعی داخل گفتار بریده شود.
    audio_filter = (
        "silenceremove="
        "start_periods=1:"
        "start_duration=0.10:"
        "start_threshold=-50dB,"
        "areverse,"
        "silenceremove="
        "start_periods=1:"
        "start_duration=0.10:"
        "start_threshold=-50dB,"
        "areverse,"
        "loudnorm=I=-19:TP=-2:LRA=11"
    )

    result = _run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-af",
            audio_filter,
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            str(temporary_path),
        ]
    )

    if result.returncode != 0 or not temporary_path.exists():
        temporary_path.unlink(missing_ok=True)
        raise AudioProcessingError(
            "FFmpeg نتوانست نمونه صدا را پردازش کند.\n\n"
            + (result.stderr.strip() or "خطای نامشخص")
        )

    metadata = inspect_audio(temporary_path)

    if metadata["duration"] < 1:
        temporary_path.unlink(missing_ok=True)
        raise AudioProcessingError(
            "بعد از حذف سکوت، گفتار قابل‌استفاده‌ای باقی نماند."
        )

    if destination_path.exists():
        destination_path.unlink()

    shutil.move(str(temporary_path), str(destination_path))
    return inspect_audio(destination_path)
