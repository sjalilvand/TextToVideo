from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


SENTENCE_ENDINGS = ("،", "؛", "؟", "!", ".", ":", "…")


def normalize_text(text: str) -> str:
    """Normalize common Persian characters and whitespace."""
    text = text.replace("\ufeff", "")
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")
    text = text.replace("ي", "ی")
    text = text.replace("ك", "ک")
    text = text.replace("ۀ", "هٔ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)

    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def format_readable_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    minutes, remainder = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(remainder, 1000)

    return f"{minutes:02}:{secs:02}.{milliseconds:03}"


def read_reference_paragraphs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    paragraphs = [
        normalize_text(paragraph)
        for paragraph in re.split(r"\n\s*\n", text)
        if normalize_text(paragraph)
    ]

    return paragraphs


def joined_length(words: list[str]) -> int:
    return len(" ".join(words))


def split_balanced(text: str, part_count: int) -> list[str]:
    """
    Split text into a requested number of approximately balanced pieces.
    Sentence endings are preferred when they are close to a balanced cut.
    """
    words = text.split()

    if not words:
        return []

    part_count = max(1, min(part_count, len(words)))

    if part_count == 1:
        return [text]

    result: list[str] = []
    remaining_words = words[:]

    for part_index in range(part_count - 1):
        remaining_parts = part_count - part_index
        target_length = joined_length(remaining_words) / remaining_parts

        max_cut = len(remaining_words) - (remaining_parts - 1)

        best_cut = 1
        best_score = float("inf")

        for cut in range(1, max_cut + 1):
            candidate_words = remaining_words[:cut]
            candidate_text = " ".join(candidate_words)
            difference = abs(len(candidate_text) - target_length)

            if candidate_text.endswith(SENTENCE_ENDINGS):
                difference *= 0.72

            if difference < best_score:
                best_score = difference
                best_cut = cut

        result.append(" ".join(remaining_words[:best_cut]))
        remaining_words = remaining_words[best_cut:]

    if remaining_words:
        result.append(" ".join(remaining_words))

    return [normalize_text(part) for part in result if normalize_text(part)]


def split_segment_text(
    text: str,
    duration: float,
    max_chars: int = 76,
    max_duration: float = 5.2,
) -> list[str]:
    """
    Choose enough subtitle pieces to keep both text and duration readable.
    """
    text = normalize_text(text)

    if not text:
        return []

    count_by_length = max(1, math.ceil(len(text) / max_chars))
    count_by_duration = max(1, math.ceil(duration / max_duration))
    part_count = max(count_by_length, count_by_duration)

    return split_balanced(text, part_count)


def create_timed_cues(
    text: str,
    start: float,
    end: float,
) -> list[dict[str, Any]]:
    duration = max(0.1, end - start)
    parts = split_segment_text(text, duration)

    if not parts:
        return []

    if len(parts) == 1:
        return [
            {
                "start": round(start, 3),
                "end": round(end, 3),
                "text": parts[0],
            }
        ]

    weights = [max(1, len(part)) for part in parts]
    total_weight = sum(weights)

    cues: list[dict[str, Any]] = []
    elapsed_weight = 0

    for index, part in enumerate(parts):
        cue_start = start + duration * elapsed_weight / total_weight
        elapsed_weight += weights[index]
        cue_end = start + duration * elapsed_weight / total_weight

        if index == 0:
            cue_start = start

        if index == len(parts) - 1:
            cue_end = end

        cues.append(
            {
                "start": round(cue_start, 3),
                "end": round(cue_end, 3),
                "text": part,
            }
        )

    return cues


def wrap_subtitle(text: str, max_line_length: int = 42) -> str:
    """Wrap a subtitle into one or two approximately balanced lines."""
    text = normalize_text(text)

    if len(text) <= max_line_length:
        return text

    words = text.split()

    if len(words) < 2:
        return text

    best_index = 1
    best_difference = float("inf")

    for index in range(1, len(words)):
        first_line = " ".join(words[:index])
        second_line = " ".join(words[index:])

        difference = abs(len(first_line) - len(second_line))

        if difference < best_difference:
            best_difference = difference
            best_index = index

    first_line = " ".join(words[:best_index])
    second_line = " ".join(words[best_index:])

    return f"{first_line}\n{second_line}"


def write_srt(
    cues: list[dict[str, Any]],
    output_path: Path,
) -> None:
    lines: list[str] = []

    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_srt_time(float(cue['start']))} --> "
            f"{format_srt_time(float(cue['end']))}"
        )
        lines.append(wrap_subtitle(str(cue["text"])))
        lines.append("")

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8-sig",
    )


def write_transcript(
    segments: list[dict[str, Any]],
    output_path: Path,
) -> None:
    lines: list[str] = []

    for segment in segments:
        start = format_readable_time(float(segment["start"]))
        end = format_readable_time(float(segment["end"]))
        text = normalize_text(str(segment["text"]))

        lines.append(f"[{start} --> {end}] {text}")

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8-sig",
    )


def align_files(
    raw_json_path: Path,
    reference_path: Path,
    output_directory: Path,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    raw_data = json.loads(
        raw_json_path.read_text(encoding="utf-8-sig")
    )

    raw_segments = raw_data.get("segments")

    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError(
            "فایل JSON فاقد بخش segments معتبر است."
        )

    reference_paragraphs = read_reference_paragraphs(reference_path)

    print("=" * 65)
    print("هم‌ترازی متن صحیح با زمان‌بندی مدل Whisper")
    print("=" * 65)
    print(f"تعداد بخش‌های فایل خام: {len(raw_segments)}")
    print(f"تعداد پاراگراف‌های مرجع: {len(reference_paragraphs)}")
    print()

    if len(reference_paragraphs) != len(raw_segments):
        raise ValueError(
            "تعداد پاراگراف‌های متن مرجع با تعداد بخش‌های گفتار "
            "برابر نیست. برای جلوگیری از زمان‌بندی اشتباه، "
            "هیچ خروجی‌ای ایجاد نشد."
        )

    corrected_segments: list[dict[str, Any]] = []
    corrected_cues: list[dict[str, Any]] = []

    for index, (raw_segment, corrected_text) in enumerate(
        zip(raw_segments, reference_paragraphs),
        start=1,
    ):
        start = float(raw_segment["start"])
        end = float(raw_segment["end"])
        raw_text = normalize_text(str(raw_segment.get("text", "")))
        corrected_text = normalize_text(corrected_text)

        corrected_segment = {
            "id": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "text": corrected_text,
            "raw_text": raw_text,
        }

        corrected_segments.append(corrected_segment)

        segment_cues = create_timed_cues(
            text=corrected_text,
            start=start,
            end=end,
        )

        for cue in segment_cues:
            cue["segment_id"] = index
            corrected_cues.append(cue)

        print(
            f"{index:02}. "
            f"[{format_readable_time(start)} --> "
            f"{format_readable_time(end)}] "
            f"{corrected_text}"
        )

    for index, cue in enumerate(corrected_cues):
        if cue["end"] <= cue["start"]:
            cue["end"] = round(cue["start"] + 0.1, 3)

        if index + 1 < len(corrected_cues):
            next_start = float(corrected_cues[index + 1]["start"])

            if cue["end"] > next_start:
                cue["end"] = round(
                    max(float(cue["start"]) + 0.05, next_start),
                    3,
                )

    srt_path = output_directory / "subtitles.corrected.srt"
    transcript_path = output_directory / "transcript.corrected.txt"
    json_path = output_directory / "transcript.corrected.json"

    write_srt(corrected_cues, srt_path)
    write_transcript(corrected_segments, transcript_path)

    corrected_result = {
        "audio": raw_data.get("audio"),
        "language": raw_data.get("language", "fa"),
        "language_probability": raw_data.get(
            "language_probability"
        ),
        "duration": raw_data.get(
            "duration",
            corrected_segments[-1]["end"],
        ),
        "model": raw_data.get("model"),
        "alignment_method": (
            "one corrected reference paragraph per Whisper segment"
        ),
        "source_json": str(raw_json_path.resolve()),
        "reference_text": str(reference_path.resolve()),
        "segments": corrected_segments,
        "subtitles": corrected_cues,
    }

    json_path.write_text(
        json.dumps(
            corrected_result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    print()
    print("=" * 65)
    print("فایل‌های اصلاح‌شده با موفقیت ایجاد شدند.")
    print(f"تعداد بخش‌های اصلاح‌شده: {len(corrected_segments)}")
    print(f"تعداد زیرنویس‌های اصلاح‌شده: {len(corrected_cues)}")
    print()
    print(f"زیرنویس نهایی: {srt_path}")
    print(f"متن نهایی: {transcript_path}")
    print(f"JSON نهایی: {json_path}")
    print("=" * 65)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Align a corrected reference transcript with "
            "Whisper segment timestamps."
        )
    )

    parser.add_argument(
        "--raw-json",
        required=True,
        help="Path to the raw Whisper transcript JSON.",
    )

    parser.add_argument(
        "--reference",
        required=True,
        help="Path to the corrected reference text.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for corrected output files.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    raw_json_path = Path(arguments.raw_json).resolve()
    reference_path = Path(arguments.reference).resolve()
    output_directory = Path(arguments.output_dir).resolve()

    if not raw_json_path.is_file():
        print(
            f"خطا: فایل JSON خام پیدا نشد: {raw_json_path}",
            file=sys.stderr,
        )
        return 1

    if not reference_path.is_file():
        print(
            f"خطا: متن مرجع پیدا نشد: {reference_path}",
            file=sys.stderr,
        )
        return 1

    try:
        align_files(
            raw_json_path=raw_json_path,
            reference_path=reference_path,
            output_directory=output_directory,
        )
        return 0
    except Exception as error:
        print(
            f"\nخطا در هم‌ترازی متن: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())