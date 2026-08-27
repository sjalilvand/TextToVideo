from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Iterable

from .model import SubtitleCue


class SrtFormatError(ValueError):
    """Raised when an SRT file cannot be parsed safely."""


class SrtService:
    TIMESTAMP_PATTERN = re.compile(
        r"^\s*"
        r"(?P<start>\d{1,3}:\d{2}:\d{2}[,.]\d{1,3})"
        r"\s*-->\s*"
        r"(?P<end>\d{1,3}:\d{2}:\d{2}[,.]\d{1,3})"
        r"(?:\s+.*)?$"
    )

    @classmethod
    def timestamp_to_ms(cls, value: str) -> int:
        cleaned = value.strip().replace(".", ",")

        match = re.fullmatch(
            r"(\d{1,3}):(\d{2}):(\d{2}),(\d{1,3})",
            cleaned,
        )

        if match is None:
            raise SrtFormatError(
                f"زمان زیرنویس نامعتبر است: {value}"
            )

        hours, minutes, seconds, milliseconds = match.groups()

        if int(minutes) > 59 or int(seconds) > 59:
            raise SrtFormatError(
                f"زمان زیرنویس خارج از محدوده است: {value}"
            )

        milliseconds = milliseconds.ljust(3, "0")[:3]

        return (
            int(hours) * 3_600_000
            + int(minutes) * 60_000
            + int(seconds) * 1_000
            + int(milliseconds)
        )

    @staticmethod
    def ms_to_timestamp(value: int) -> str:
        total_ms = max(0, int(value))

        hours, remainder = divmod(total_ms, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        seconds, milliseconds = divmod(remainder, 1_000)

        return (
            f"{hours:02d}:{minutes:02d}:{seconds:02d},"
            f"{milliseconds:03d}"
        )

    @classmethod
    def parse(cls, content: str) -> list[SubtitleCue]:
        normalized = (
            content
            .replace("\ufeff", "")
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

        if not normalized:
            return []

        blocks = re.split(r"\n[ \t]*\n+", normalized)
        cues: list[SubtitleCue] = []

        for block_number, block in enumerate(blocks, start=1):
            lines = block.splitlines()

            while lines and not lines[0].strip():
                lines.pop(0)

            while lines and not lines[-1].strip():
                lines.pop()

            if not lines:
                continue

            timestamp_line_index: int | None = None
            timestamp_match = None

            for line_index, line in enumerate(lines[:3]):
                possible_match = cls.TIMESTAMP_PATTERN.match(line)

                if possible_match is not None:
                    timestamp_line_index = line_index
                    timestamp_match = possible_match
                    break

            if timestamp_line_index is None or timestamp_match is None:
                preview = " | ".join(lines[:3])

                raise SrtFormatError(
                    "خط زمان در بلوک "
                    f"{block_number} پیدا نشد: {preview}"
                )

            if timestamp_line_index > 0:
                raw_index = lines[0].strip()

                if raw_index.isdigit():
                    cue_index = int(raw_index)
                else:
                    cue_index = len(cues) + 1
            else:
                cue_index = len(cues) + 1

            start_ms = cls.timestamp_to_ms(
                timestamp_match.group("start")
            )
            end_ms = cls.timestamp_to_ms(
                timestamp_match.group("end")
            )

            text_lines = lines[timestamp_line_index + 1:]
            text = "\n".join(text_lines).strip()

            cue = SubtitleCue(
                index=cue_index,
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
            ).normalized()

            cue_errors = cue.validate()

            if cue_errors:
                raise SrtFormatError(
                    f"خطا در بلوک {block_number}: "
                    + "؛ ".join(cue_errors)
                )

            cues.append(cue)

        cls.reindex(cues)
        return cues

    @classmethod
    def load(cls, path: str | Path) -> list[SubtitleCue]:
        subtitle_path = Path(path)

        if not subtitle_path.exists():
            raise FileNotFoundError(
                f"فایل زیرنویس پیدا نشد: {subtitle_path}"
            )

        if not subtitle_path.is_file():
            raise SrtFormatError(
                f"مسیر زیرنویس یک فایل نیست: {subtitle_path}"
            )

        content = subtitle_path.read_text(encoding="utf-8-sig")
        return cls.parse(content)

    @classmethod
    def serialize(
        cls,
        cues: Iterable[SubtitleCue],
        *,
        reindex: bool = True,
    ) -> str:
        normalized_cues = [
            cue.normalized()
            for cue in cues
        ]

        blocks: list[str] = []

        for position, cue in enumerate(
            normalized_cues,
            start=1,
        ):
            errors = cue.validate()

            if errors:
                raise SrtFormatError(
                    f"خطا در زیرنویس {position}: "
                    + "؛ ".join(errors)
                )

            output_index = position if reindex else cue.index

            blocks.append(
                f"{output_index}\n"
                f"{cls.ms_to_timestamp(cue.start_ms)} --> "
                f"{cls.ms_to_timestamp(cue.end_ms)}\n"
                f"{cue.text}"
            )

        if not blocks:
            return ""

        return "\n\n".join(blocks) + "\n"

    @classmethod
    def save(
        cls,
        path: str | Path,
        cues: Iterable[SubtitleCue],
        *,
        reindex: bool = True,
    ) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        content = cls.serialize(
            cues,
            reindex=reindex,
        )

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                suffix=".srt.tmp",
                prefix=f"{output_path.stem}-",
                dir=str(output_path.parent),
                delete=False,
            ) as temporary_file:
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)

            os.replace(temporary_path, output_path)

        except Exception:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            raise

        return output_path

    @staticmethod
    def reindex(cues: list[SubtitleCue]) -> None:
        for index, cue in enumerate(cues, start=1):
            cue.index = index

    @staticmethod
    def shift(
        cues: Iterable[SubtitleCue],
        offset_ms: int,
    ) -> list[SubtitleCue]:
        shifted: list[SubtitleCue] = []

        for cue in cues:
            start_ms = max(0, cue.start_ms + int(offset_ms))
            end_ms = max(start_ms + 1, cue.end_ms + int(offset_ms))

            shifted.append(
                cue.clone(
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )

        SrtService.reindex(shifted)
        return shifted

    @staticmethod
    def validate_timeline(
        cues: Iterable[SubtitleCue],
    ) -> list[str]:
        cue_list = list(cues)
        warnings: list[str] = []

        for position, cue in enumerate(cue_list):
            errors = cue.validate()

            for error in errors:
                warnings.append(
                    f"زیرنویس {position + 1}: {error}"
                )

            if position == 0:
                continue

            previous = cue_list[position - 1]

            if cue.start_ms < previous.start_ms:
                warnings.append(
                    f"ترتیب زمانی زیرنویس {position + 1} "
                    "نادرست است."
                )

            if cue.start_ms < previous.end_ms:
                overlap = previous.end_ms - cue.start_ms

                warnings.append(
                    f"زیرنویس‌های {position} و "
                    f"{position + 1} به اندازه "
                    f"{overlap} میلی‌ثانیه هم‌پوشانی دارند."
                )

        return warnings
