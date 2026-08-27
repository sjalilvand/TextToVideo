from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel


PERSIAN_ENDINGS = ("،", "؛", "؟", "!", ".", ":", "…")


def normalize_text(text: str) -> str:
    """Normalize spaces and common Arabic characters in Persian text."""
    text = text.replace("\u200f", "")
    text = text.replace("\u200e", "")
    text = text.replace("ي", "ی")
    text = text.replace("ك", "ک")
    text = text.replace("ۀ", "هٔ")
    text = re.sub(r"\s+", " ", text)
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


def wrap_subtitle(text: str, max_line_length: int = 42) -> str:
    """
    Wrap Persian subtitle into at most two readable lines.
    """
    text = normalize_text(text)

    if len(text) <= max_line_length:
        return text

    words = text.split()
    if len(words) < 2:
        return text

    best_index = 1
    best_difference = len(text)

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


def create_cues_from_words(
    words: list[dict[str, Any]],
    max_chars: int = 76,
    max_duration: float = 5.5,
    min_break_duration: float = 1.6,
) -> list[dict[str, Any]]:
    """
    Convert word timestamps into readable subtitle cues.
    """
    cues: list[dict[str, Any]] = []
    current_words: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal current_words

        if not current_words:
            return

        text = normalize_text(
            " ".join(str(item["text"]).strip() for item in current_words)
        )

        if text:
            cues.append(
                {
                    "start": float(current_words[0]["start"]),
                    "end": float(current_words[-1]["end"]),
                    "text": text,
                }
            )

        current_words = []

    for word in words:
        word_text = normalize_text(str(word.get("text", "")))

        if not word_text:
            continue

        item = {
            "start": float(word["start"]),
            "end": float(word["end"]),
            "text": word_text,
        }

        if not current_words:
            current_words.append(item)
            continue

        candidate_text = normalize_text(
            " ".join(
                [str(existing["text"]) for existing in current_words]
                + [word_text]
            )
        )

        candidate_duration = item["end"] - current_words[0]["start"]

        if (
            len(candidate_text) > max_chars
            or candidate_duration > max_duration
        ):
            flush()
            current_words.append(item)
            continue

        current_words.append(item)

        current_text = str(current_words[-1]["text"])
        current_duration = (
            current_words[-1]["end"] - current_words[0]["start"]
        )

        if (
            current_text.endswith(PERSIAN_ENDINGS)
            and current_duration >= min_break_duration
        ):
            flush()

    flush()

    for index, cue in enumerate(cues):
        if cue["end"] <= cue["start"]:
            cue["end"] = cue["start"] + 0.8

        if index + 1 < len(cues):
            next_start = cues[index + 1]["start"]

            if cue["end"] >= next_start:
                cue["end"] = max(cue["start"] + 0.1, next_start - 0.03)

    return cues


def create_cues_from_segments(
    segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []

    for segment in segments:
        text = normalize_text(str(segment["text"]))

        if not text:
            continue

        cues.append(
            {
                "start": float(segment["start"]),
                "end": float(segment["end"]),
                "text": text,
            }
        )

    return cues


def write_srt(cues: list[dict[str, Any]], output_path: Path) -> None:
    lines: list[str] = []

    for index, cue in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_srt_time(cue['start'])} --> "
            f"{format_srt_time(cue['end'])}"
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


def transcribe_audio(
    audio_path: Path,
    output_directory: Path,
    model_name: str,
) -> None:
    output_directory.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("تبدیل صدای فارسی به متن و زیرنویس زمان‌بندی‌شده")
    print("=" * 60)
    print(f"فایل صوتی: {audio_path}")
    print(f"مدل تشخیص گفتار: {model_name}")
    print("دستگاه پردازش: CPU")
    print("نوع محاسبات: INT8")
    print()

    cpu_threads = max(2, min(6, os.cpu_count() or 4))

    print("در حال بارگذاری مدل...")
    print("در اجرای اول، فایل‌های مدل از اینترنت دانلود می‌شوند.")
    print()

    model = WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads,
        num_workers=1,
    )

    print("مدل آماده شد.")
    print("در حال شناسایی گفتار فارسی...")
    print("این مرحله ممکن است چند دقیقه زمان ببرد.")
    print()

    segment_generator, info = model.transcribe(
        str(audio_path),
        language="fa",
        beam_size=5,
        best_of=5,
        temperature=0.0,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 350,
            "speech_pad_ms": 200,
        },
        word_timestamps=True,
        condition_on_previous_text=True,
        initial_prompt=(
            "این یک آموزش فارسی درباره همزمانی در پایتون است. "
            "اصطلاحات تخصصی درس عبارت‌اند از: "
            "همزمانی، Concurrency، تردینگ، Threading، ترد، Thread، "
            "مالتی‌پروسسینگ، Multiprocessing، پراسس، Process، "
            "ای‌سینک، Async، اویت، Await، asyncio، "
            "ورودی و خروجی، I/O-bound، آی‌او باند، "
            "پردازنده، CPU-bound، سی‌پی‌یو باند، "
            "محدودیت GIL، جی‌آی‌ال، API، ای‌پی‌آی، "
            "درخواست شبکه، وب‌سوکت، پردازش تصویر، "
            "محاسبات علمی، هوش مصنوعی، متد start و متد join."
        ),
    )

    segments: list[dict[str, Any]] = []
    all_words: list[dict[str, Any]] = []

    for number, segment in enumerate(segment_generator, start=1):
        segment_text = normalize_text(segment.text)

        segment_words: list[dict[str, Any]] = []

        if segment.words:
            for word in segment.words:
                if word.start is None or word.end is None:
                    continue

                word_text = normalize_text(word.word)

                if not word_text:
                    continue

                word_item = {
                    "start": round(float(word.start), 3),
                    "end": round(float(word.end), 3),
                    "text": word_text,
                    "probability": (
                        round(float(word.probability), 4)
                        if word.probability is not None
                        else None
                    ),
                }

                segment_words.append(word_item)
                all_words.append(word_item)

        segment_item = {
            "id": number,
            "start": round(float(segment.start), 3),
            "end": round(float(segment.end), 3),
            "text": segment_text,
            "words": segment_words,
        }

        segments.append(segment_item)

        print(
            f"[{format_readable_time(segment.start)} --> "
            f"{format_readable_time(segment.end)}] "
            f"{segment_text}"
        )

    if not segments:
        raise RuntimeError(
            "هیچ گفتاری در فایل صوتی شناسایی نشد."
        )

    if all_words:
        cues = create_cues_from_words(all_words)
    else:
        cues = create_cues_from_segments(segments)

    srt_path = output_directory / "subtitles.srt"
    transcript_path = output_directory / "transcript.txt"
    json_path = output_directory / "transcript.json"

    write_srt(cues, srt_path)
    write_transcript(segments, transcript_path)

    result = {
        "audio": str(audio_path.resolve()),
        "language": getattr(info, "language", "fa"),
        "language_probability": round(
            float(getattr(info, "language_probability", 0.0)),
            4,
        ),
        "duration": round(
            float(getattr(info, "duration", segments[-1]["end"])),
            3,
        ),
        "model": model_name,
        "segments": segments,
        "subtitles": cues,
    }

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )

    print()
    print("=" * 60)
    print("تبدیل صدا با موفقیت انجام شد.")
    print(f"تعداد بخش‌های گفتار: {len(segments)}")
    print(f"تعداد زیرنویس‌ها: {len(cues)}")
    print(f"زبان شناسایی‌شده: {result['language']}")
    print(
        "احتمال زبان: "
        f"{result['language_probability'] * 100:.2f}%"
    )
    print()
    print(f"زیرنویس: {srt_path}")
    print(f"متن گفتار: {transcript_path}")
    print(f"اطلاعات زمان‌بندی: {json_path}")
    print("=" * 60)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Persian narration to SRT and JSON."
    )

    parser.add_argument(
        "--audio",
        required=True,
        help="Path to the narration audio file.",
    )

    parser.add_argument(
        "--output-dir",
        default=r"D:\TextToVideo\temp",
        help="Directory for generated subtitle files.",
    )

    parser.add_argument(
        "--model",
        default="small",
        help="Whisper model name, for example: base, small, medium.",
    )

    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()

    audio_path = Path(arguments.audio).resolve()
    output_directory = Path(arguments.output_dir).resolve()

    if not audio_path.is_file():
        print(
            f"خطا: فایل صوتی پیدا نشد: {audio_path}",
            file=sys.stderr,
        )
        return 1

    try:
        transcribe_audio(
            audio_path=audio_path,
            output_directory=output_directory,
            model_name=arguments.model,
        )
        return 0
    except KeyboardInterrupt:
        print("\nعملیات توسط کاربر متوقف شد.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"\nخطا در تبدیل صدا: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())