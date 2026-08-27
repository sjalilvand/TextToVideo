from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import edge_tts
from PySide6.QtCore import QThread, Signal


class TTSWorker(QThread):
    progress_changed = Signal(int, str)
    result_ready = Signal(str, str, str, str)
    error_occurred = Signal(str)

    def __init__(
        self,
        text: str,
        voice: str,
        rate: int,
        pitch: int,
        max_words: int,
        output_directory: Path,
        output_stem: str,
        mode: str = "full",
        parent=None,
    ):
        super().__init__(parent)

        self.text = text.strip()
        self.voice = voice
        self.rate = int(rate)
        self.pitch = int(pitch)
        self.max_words = max(1, int(max_words))
        self.output_directory = Path(output_directory)
        self.output_stem = self.sanitize_filename(output_stem)
        self.mode = mode

    def run(self):
        try:
            asyncio.run(self.generate())
        except Exception as error:
            self.error_occurred.emit(
                f"{type(error).__name__}: {error}"
            )

    async def generate(self):
        if not self.text:
            raise ValueError("متنی برای تبدیل به صدا وجود ندارد.")

        self.output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        mp3_path = (
            self.output_directory /
            f"{self.output_stem}.mp3"
        )

        srt_path = (
            self.output_directory /
            f"{self.output_stem}.srt"
        )

        timing_path = (
            self.output_directory /
            f"{self.output_stem}.words.json"
        )

        temporary_mp3_path = mp3_path.with_suffix(".mp3.part")

        for path in (
            temporary_mp3_path,
            mp3_path,
            srt_path,
            timing_path,
        ):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

        rate_value = self.format_rate(self.rate)
        pitch_value = self.format_pitch(self.pitch)

        self.progress_changed.emit(
            5,
            "در حال اتصال به سرویس Edge-TTS..."
        )

        communicator = edge_tts.Communicate(
            text=self.text,
            voice=self.voice,
            rate=rate_value,
            pitch=pitch_value,
        )

        word_boundaries = []
        audio_chunks = 0

        try:
            with temporary_mp3_path.open("wb") as audio_file:
                async for chunk in communicator.stream():
                    chunk_type = chunk.get("type")

                    if chunk_type == "audio":
                        audio_data = chunk.get("data", b"")

                        if audio_data:
                            audio_file.write(audio_data)
                            audio_chunks += 1

                            progress = min(
                                70,
                                10 + audio_chunks,
                            )

                            self.progress_changed.emit(
                                progress,
                                "در حال دریافت و ساخت فایل صوتی..."
                            )

                    elif (
                        str(chunk_type).casefold()
                        == "wordboundary"
                    ):
                        offset = int(chunk.get("offset", 0))
                        duration = int(chunk.get("duration", 0))
                        word = str(chunk.get("text", "")).strip()

                        if word:
                            word_boundaries.append({
                                "index": len(word_boundaries) + 1,
                                "word": word,
                                "offset": offset,
                                "duration": duration,
                                "start_ms": self.ticks_to_ms(offset),
                                "end_ms": self.ticks_to_ms(
                                    offset + duration
                                ),
                            })

            if not temporary_mp3_path.exists():
                raise RuntimeError(
                    "هیچ داده صوتی از Edge-TTS دریافت نشد."
                )

            if temporary_mp3_path.stat().st_size == 0:
                raise RuntimeError(
                    "فایل صوتی تولیدشده خالی است."
                )

            temporary_mp3_path.replace(mp3_path)

            timing_source = "edge-word-boundary"
            audio_duration_ms = self.probe_audio_duration_ms(
                mp3_path
            )

            if not word_boundaries:
                self.progress_changed.emit(
                    74,
                    "زمان‌بندی کلمات دریافت نشد؛ "
                    "در حال ساخت زمان‌بندی جایگزین..."
                )

                word_boundaries = (
                    self.create_estimated_word_boundaries(
                        self.text,
                        audio_duration_ms,
                    )
                )

                timing_source = (
                    "estimated-from-audio-duration"
                )

            self.progress_changed.emit(
                76,
                "فایل MP3 ساخته شد؛ در حال تولید زیرنویس..."
            )

            subtitles = self.create_subtitles(
                word_boundaries,
                self.max_words,
            )

            srt_content = self.create_srt(subtitles)

            srt_path.write_text(
                srt_content,
                encoding="utf-8-sig",
            )

            self.progress_changed.emit(
                88,
                "در حال ذخیره زمان‌بندی کلمات..."
            )

            timing_data = {
                "text": self.text,
                "voice": self.voice,
                "rate": self.rate,
                "pitch": self.pitch,
                "timing_source": timing_source,
                "audio_duration_ms": audio_duration_ms,
                "word_count": len(word_boundaries),
                "subtitle_count": len(subtitles),
                "words": word_boundaries,
                "subtitles": subtitles,
            }

            timing_path.write_text(
                json.dumps(
                    timing_data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            self.progress_changed.emit(
                100,
                "تولید صدا و زیرنویس با موفقیت کامل شد."
            )

            self.result_ready.emit(
                str(mp3_path),
                str(srt_path),
                str(timing_path),
                self.mode,
            )

        except Exception:
            try:
                if temporary_mp3_path.exists():
                    temporary_mp3_path.unlink()
            except OSError:
                pass

            raise

    @staticmethod
    def probe_audio_duration_ms(audio_path: Path) -> int:
        ffprobe_path = shutil.which("ffprobe")

        if ffprobe_path:
            command = [
                ffprobe_path,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ]

            creation_flags = 0

            if os.name == "nt":
                creation_flags = getattr(
                    subprocess,
                    "CREATE_NO_WINDOW",
                    0,
                )

            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                    check=True,
                    creationflags=creation_flags,
                )

                duration_seconds = float(
                    result.stdout.strip()
                )

                if duration_seconds > 0:
                    return max(
                        1,
                        round(duration_seconds * 1000),
                    )
            except (
                OSError,
                ValueError,
                subprocess.SubprocessError,
            ):
                pass

        # Edge-TTS معمولاً MP3 با نرخ حدود 48 kb/s تولید می‌کند.
        # این بخش فقط در صورت در دسترس نبودن ffprobe استفاده می‌شود.
        if audio_path.exists():
            estimated_ms = round(
                audio_path.stat().st_size
                * 8
                / 48_000
                * 1000
            )

            if estimated_ms > 0:
                return estimated_ms

        raise RuntimeError(
            "مدت فایل صوتی قابل تشخیص نیست."
        )

    @staticmethod
    def create_estimated_word_boundaries(
        text: str,
        duration_ms: int,
    ) -> list[dict]:
        matches = list(re.finditer(r"\S+", text))

        if not matches:
            return []

        duration_ms = max(1000, int(duration_ms))
        weights: list[float] = []

        for index, match in enumerate(matches):
            word = match.group(0)
            plain_word = re.sub(
                r"[^\w\u0600-\u06FF]+",
                "",
                word,
            )

            weight = max(
                1.0,
                min(12, len(plain_word)) * 0.55,
            )

            if re.search(r"[,،؛;:]$", word):
                weight += 1.2

            if re.search(r"[.!؟?]$", word):
                weight += 2.5

            if index + 1 < len(matches):
                gap = text[
                    match.end():
                    matches[index + 1].start()
                ]

                if "\n" in gap:
                    weight += 1.8

            weights.append(weight)

        total_weight = sum(weights)

        if total_weight <= 0:
            total_weight = float(len(matches))
            weights = [1.0] * len(matches)

        words: list[dict] = []
        elapsed_weight = 0.0
        previous_end_ms = 0

        for index, (match, weight) in enumerate(
            zip(matches, weights),
            start=1,
        ):
            start_ms = previous_end_ms
            elapsed_weight += weight

            if index == len(matches):
                end_ms = duration_ms
            else:
                end_ms = round(
                    duration_ms
                    * elapsed_weight
                    / total_weight
                )

            end_ms = max(start_ms + 1, end_ms)
            end_ms = min(duration_ms, end_ms)

            words.append({
                "index": index,
                "word": match.group(0),
                "offset": start_ms * 10_000,
                "duration": (
                    end_ms - start_ms
                ) * 10_000,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "estimated": True,
            })

            previous_end_ms = end_ms

        return words

    @staticmethod
    def format_rate(value: int) -> str:
        if value >= 0:
            return f"+{value}%"

        return f"{value}%"

    @staticmethod
    def format_pitch(value: int) -> str:
        if value >= 0:
            return f"+{value}Hz"

        return f"{value}Hz"

    @staticmethod
    def ticks_to_ms(value: int) -> int:
        # زمان‌های Edge-TTS بر حسب واحدهای ۱۰۰ نانوثانیه هستند.
        return max(0, round(value / 10_000))

    @staticmethod
    def sanitize_filename(value: str) -> str:
        value = re.sub(r'[<>:"/\\|?*]+', "-", value)
        value = re.sub(r"\s+", "-", value.strip())
        value = value.strip(".-")

        return value or "narration"

    @staticmethod
    def create_subtitles(words: list[dict], max_words: int) -> list[dict]:
        if not words:
            return []

        subtitles = []

        for start_index in range(0, len(words), max_words):
            group = words[start_index:start_index + max_words]

            start_ms = int(group[0]["start_ms"])
            end_ms = int(group[-1]["end_ms"])

            if end_ms <= start_ms:
                end_ms = start_ms + 300

            text = " ".join(
                item["word"] for item in group
            ).strip()

            subtitles.append({
                "index": len(subtitles) + 1,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "text": text,
                "word_start_index": group[0]["index"],
                "word_end_index": group[-1]["index"],
            })

        return subtitles

    @classmethod
    def create_srt(cls, subtitles: list[dict]) -> str:
        blocks = []

        for subtitle in subtitles:
            blocks.append(
                f'{subtitle["index"]}\n'
                f'{cls.format_srt_time(subtitle["start_ms"])} --> '
                f'{cls.format_srt_time(subtitle["end_ms"])}\n'
                f'{subtitle["text"]}'
            )

        if not blocks:
            return ""

        return "\n\n".join(blocks) + "\n"

    @staticmethod
    def format_srt_time(milliseconds: int) -> str:
        milliseconds = max(0, int(milliseconds))

        hours, remainder = divmod(
            milliseconds,
            3_600_000,
        )

        minutes, remainder = divmod(
            remainder,
            60_000,
        )

        seconds, milliseconds = divmod(
            remainder,
            1_000,
        )

        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{seconds:02d},"
            f"{milliseconds:03d}"
        )