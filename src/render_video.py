from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


PROJECT = Path(r"D:\TextToVideo")
HTML_PATH = PROJECT / "input" / "lesson.html"
AUDIO_PATH = PROJECT / "input" / "narration.mp3"

TRANSCRIPT_PATH = (
    PROJECT
    / "temp"
    / "final-transcription"
    / "transcript.corrected.json"
)

SUBTITLE_PATH = (
    PROJECT
    / "temp"
    / "final-transcription"
    / "subtitles.corrected.srt"
)

LAYOUT_PATH = (
    PROJECT
    / "temp"
    / "lesson-layout-report.json"
)

OUTPUT_DIR = PROJECT / "output"
TEMP_VIDEO_DIR = PROJECT / "temp" / "playwright-video"
SCENE_PLAN_PATH = PROJECT / "temp" / "video-scene-plan.json"

VIEWPORT_WIDTH = 1080
VIEWPORT_HEIGHT = 1920
EXPECTED_SEGMENTS = 36

OUTPUT_NAME = os.environ.get(
    "OUTPUT_NAME",
    "html-video-silent.webm",
)

RENDER_LIMIT = os.environ.get("RENDER_SECONDS", "").strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_time(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    if not isinstance(value, str):
        raise ValueError(f"مقدار زمان نامعتبر است: {value!r}")

    value = value.strip().replace(",", ".")

    if not value:
        raise ValueError("مقدار زمان خالی است.")

    if ":" not in value:
        return float(value)

    parts = value.split(":")

    if len(parts) == 3:
        hours, minutes, seconds = parts
        return (
            float(hours) * 3600
            + float(minutes) * 60
            + float(seconds)
        )

    if len(parts) == 2:
        minutes, seconds = parts
        return float(minutes) * 60 + float(seconds)

    raise ValueError(f"فرمت زمان نامعتبر است: {value}")


def get_first(item: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]

    return None


def normalize_segment(item: dict[str, Any]) -> dict[str, Any] | None:
    start_value = get_first(
        item,
        (
            "start",
            "start_time",
            "startTime",
            "begin",
            "from",
        ),
    )

    end_value = get_first(
        item,
        (
            "end",
            "end_time",
            "endTime",
            "finish",
            "to",
        ),
    )

    if start_value is None or end_value is None:
        return None

    try:
        start = parse_time(start_value)
        end = parse_time(end_value)
    except (TypeError, ValueError):
        return None

    if end <= start:
        return None

    text_value = get_first(
        item,
        (
            "corrected_text",
            "correctedText",
            "corrected",
            "reference_text",
            "referenceText",
            "text",
            "transcript",
            "content",
        ),
    )

    text = str(text_value or "").strip()

    return {
        "start": round(start, 3),
        "end": round(end, 3),
        "text": text,
    }


def find_segment_candidates(
    node: Any,
    path: str = "root",
) -> list[tuple[float, str, list[dict[str, Any]]]]:
    candidates: list[
        tuple[float, str, list[dict[str, Any]]]
    ] = []

    if isinstance(node, dict):
        for key, value in node.items():
            candidates.extend(
                find_segment_candidates(
                    value,
                    f"{path}.{key}",
                )
            )

    elif isinstance(node, list):
        normalized: list[dict[str, Any]] = []

        for item in node:
            if isinstance(item, dict):
                segment = normalize_segment(item)

                if segment is not None:
                    normalized.append(segment)

        if len(normalized) >= 2:
            lower_path = path.lower()

            score = abs(
                len(normalized) - EXPECTED_SEGMENTS
            ) * 10

            if "segment" in lower_path:
                score -= 25

            if "paragraph" in lower_path:
                score -= 10

            if "subtitle" in lower_path:
                score += 25

            candidates.append(
                (
                    score,
                    path,
                    normalized,
                )
            )

        for index, value in enumerate(node):
            if isinstance(value, (dict, list)):
                candidates.extend(
                    find_segment_candidates(
                        value,
                        f"{path}[{index}]",
                    )
                )

    return candidates


def load_speech_segments() -> tuple[list[dict[str, Any]], str]:
    data = read_json(TRANSCRIPT_PATH)
    candidates = find_segment_candidates(data)

    if not candidates:
        raise RuntimeError(
            "هیچ فهرست زمان‌بندی‌شده‌ای در JSON پیدا نشد."
        )

    candidates.sort(
        key=lambda item: (
            item[0],
            abs(len(item[2]) - EXPECTED_SEGMENTS),
            item[1],
        )
    )

    _, selected_path, segments = candidates[0]

    segments.sort(key=lambda item: item["start"])

    return segments, selected_path


def parse_srt(path: Path) -> list[dict[str, Any]]:
    content = path.read_text(
        encoding="utf-8-sig",
    ).replace("\r\n", "\n")

    blocks = re.split(r"\n{2,}", content.strip())
    cues: list[dict[str, Any]] = []

    timestamp_pattern = re.compile(
        r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
        r"\s*-->\s*"
        r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{3})"
    )

    for block in blocks:
        lines = [
            line.strip()
            for line in block.splitlines()
            if line.strip()
        ]

        if not lines:
            continue

        timestamp_index = None
        match = None

        for index, line in enumerate(lines):
            match = timestamp_pattern.search(line)

            if match:
                timestamp_index = index
                break

        if match is None or timestamp_index is None:
            continue

        text_lines = lines[timestamp_index + 1 :]
        text = "\n".join(text_lines).strip()

        if not text:
            continue

        cues.append(
            {
                "start": round(
                    parse_time(match.group("start")),
                    3,
                ),
                "end": round(
                    parse_time(match.group("end")),
                    3,
                ),
                "text": text,
            }
        )

    cues.sort(key=lambda cue: cue["start"])

    return cues


def get_audio_duration() -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(AUDIO_PATH),
    ]

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    return float(result.stdout.strip())


def build_scenes(
    segments: list[dict[str, Any]],
    layout: dict[str, Any],
) -> list[dict[str, Any]]:
    max_scroll = int(layout["maxScroll"])

    headings = []

    for heading in layout.get("headings", []):
        text = str(heading.get("text", "")).strip()
        top = int(heading.get("top", 0))

        lower_text = text.lower()

        if (
            "mahai.ir" in lower_text
            or "شرکت ماه افزار" in text
        ):
            continue

        headings.append(
            {
                "text": text,
                "top": top,
            }
        )

    if not headings:
        raise RuntimeError(
            "عنوانی برای صحنه‌بندی پیدا نشد."
        )

    scenes: list[dict[str, Any]] = []
    segment_count = len(segments)
    heading_count = len(headings)

    for index, segment in enumerate(segments):
        if segment_count <= 1:
            heading_index = 0
        else:
            heading_index = round(
                index
                * (heading_count - 1)
                / (segment_count - 1)
            )

        heading = headings[heading_index]

        # عنوان نزدیک بالای قاب قرار می‌گیرد، اما کمی حاشیه دارد.
        target_scroll = max(
            0,
            min(
                max_scroll,
                int(heading["top"]) - 170,
            ),
        )

        scenes.append(
            {
                "index": index + 1,
                "start": segment["start"],
                "end": segment["end"],
                "speechText": segment["text"],
                "headingIndex": heading_index + 1,
                "headingText": heading["text"],
                "targetScroll": target_scroll,
            }
        )

    return scenes


def validate_files() -> None:
    required_files = [
        HTML_PATH,
        AUDIO_PATH,
        TRANSCRIPT_PATH,
        SUBTITLE_PATH,
        LAYOUT_PATH,
    ]

    missing = [
        path
        for path in required_files
        if not path.is_file()
    ]

    if missing:
        formatted = "\n".join(
            f"  - {path}" for path in missing
        )

        raise FileNotFoundError(
            "فایل‌های زیر پیدا نشدند:\n"
            f"{formatted}"
        )


def main() -> int:
    validate_files()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_PLAN_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    speech_segments, selected_path = (
        load_speech_segments()
    )

    subtitle_cues = parse_srt(SUBTITLE_PATH)
    layout = read_json(LAYOUT_PATH)
    audio_duration = get_audio_duration()

    render_duration = audio_duration

    if RENDER_LIMIT:
        render_duration = min(
            audio_duration,
            float(RENDER_LIMIT),
        )

    scenes = build_scenes(
        speech_segments,
        layout,
    )

    scene_plan = {
        "audioDuration": round(audio_duration, 3),
        "renderDuration": round(render_duration, 3),
        "selectedTranscriptPath": selected_path,
        "speechSegmentCount": len(speech_segments),
        "subtitleCueCount": len(subtitle_cues),
        "viewport": {
            "width": VIEWPORT_WIDTH,
            "height": VIEWPORT_HEIGHT,
        },
        "scenes": scenes,
    }

    SCENE_PLAN_PATH.write_text(
        json.dumps(
            scene_plan,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8-sig",
    )

    output_path = OUTPUT_DIR / OUTPUT_NAME

    if output_path.exists():
        output_path.unlink()

    print("=" * 68)
    print("آماده‌سازی ضبط ویدئو")
    print("=" * 68)
    print(f"مسیر JSON انتخاب‌شده: {selected_path}")
    print(f"تعداد بخش‌های گفتار: {len(speech_segments)}")
    print(f"تعداد زیرنویس‌ها: {len(subtitle_cues)}")
    print(f"مدت کامل صوت: {audio_duration:.3f} ثانیه")
    print(f"مدت این رندر: {render_duration:.3f} ثانیه")
    print(f"خروجی: {output_path}")
    print()

    animation_data = {
        "duration": render_duration,
        "scenes": scenes,
        "subtitles": subtitle_cues,
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
                "--hide-scrollbars",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )

        context = browser.new_context(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
            locale="fa-IR",
            record_video_dir=str(TEMP_VIDEO_DIR),
            record_video_size={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
        )

        page = context.new_page()
        page.set_default_timeout(0)

        page.goto(
            HTML_PATH.resolve().as_uri(),
            wait_until="load",
            timeout=60_000,
        )

        page.evaluate(
            """
            async (data) => {
                if (document.fonts && document.fonts.ready) {
                    await document.fonts.ready;
                }

                document.documentElement.style.scrollBehavior = 'auto';
                document.documentElement.style.overflowX = 'hidden';
                document.body.style.overflowX = 'hidden';

                const style = document.createElement('style');

                style.textContent = `
                    html, body {
                        scrollbar-width: none !important;
                    }

                    html::-webkit-scrollbar,
                    body::-webkit-scrollbar {
                        display: none !important;
                    }

                    #ttv-subtitle-box {
                        position: fixed;
                        right: 50%;
                        bottom: 155px;
                        transform: translateX(50%);
                        width: calc(100% - 90px);
                        max-width: 990px;
                        box-sizing: border-box;
                        padding: 22px 30px 24px;
                        border-radius: 24px;
                        color: #ffffff;
                        background: rgba(8, 12, 20, 0.88);
                        border: 2px solid rgba(255, 255, 255, 0.18);
                        box-shadow: 0 14px 42px rgba(0, 0, 0, 0.42);
                        font-family:
                            Tahoma,
                            "Segoe UI",
                            Arial,
                            sans-serif;
                        font-size: 43px;
                        font-weight: 700;
                        line-height: 1.65;
                        text-align: center;
                        direction: rtl;
                        white-space: pre-line;
                        z-index: 2147483647;
                        opacity: 0;
                    }

                    #ttv-progress {
                        position: fixed;
                        right: 0;
                        bottom: 0;
                        height: 8px;
                        width: 0;
                        background: linear-gradient(
                            90deg,
                            #22c55e,
                            #38bdf8
                        );
                        z-index: 2147483647;
                    }
                `;

                document.head.appendChild(style);

                const subtitleBox = document.createElement('div');
                subtitleBox.id = 'ttv-subtitle-box';
                subtitleBox.setAttribute('dir', 'rtl');
                document.body.appendChild(subtitleBox);

                const progress = document.createElement('div');
                progress.id = 'ttv-progress';
                document.body.appendChild(progress);

                const scenes = data.scenes;
                const subtitles = data.subtitles;
                const duration = Number(data.duration);

                const easeInOut = (value) => {
                    const x = Math.max(0, Math.min(1, value));

                    return x < 0.5
                        ? 4 * x * x * x
                        : 1 - Math.pow(-2 * x + 2, 3) / 2;
                };

                let sceneIndex = 0;
                let subtitleIndex = 0;
                let lastSubtitleText = null;

                window.scrollTo(0, scenes[0]?.targetScroll || 0);

                await new Promise((resolve) => {
                    const startedAt = performance.now();

                    const renderFrame = (now) => {
                        const elapsed =
                            (now - startedAt) / 1000;

                        while (
                            sceneIndex < scenes.length - 1 &&
                            elapsed >= scenes[sceneIndex].end
                        ) {
                            sceneIndex += 1;
                        }

                        const scene = scenes[sceneIndex];

                        if (scene) {
                            const previousTarget =
                                sceneIndex > 0
                                    ? scenes[sceneIndex - 1]
                                        .targetScroll
                                    : scene.targetScroll;

                            const sceneDuration = Math.max(
                                0.05,
                                scene.end - scene.start
                            );

                            const transitionDuration = Math.min(
                                1.35,
                                Math.max(
                                    0.45,
                                    sceneDuration * 0.28
                                )
                            );

                            const localTime = Math.max(
                                0,
                                elapsed - scene.start
                            );

                            const transitionProgress =
                                easeInOut(
                                    localTime
                                    / transitionDuration
                                );

                            const scrollPosition =
                                previousTarget
                                + (
                                    scene.targetScroll
                                    - previousTarget
                                )
                                * transitionProgress;

                            window.scrollTo(
                                0,
                                Math.round(scrollPosition)
                            );
                        }

                        while (
                            subtitleIndex <
                                subtitles.length - 1 &&
                            elapsed >=
                                subtitles[subtitleIndex].end
                        ) {
                            subtitleIndex += 1;
                        }

                        const cue = subtitles[subtitleIndex];

                        const activeCue =
                            cue &&
                            elapsed >= cue.start &&
                            elapsed < cue.end
                                ? cue
                                : null;

                        const subtitleText =
                            activeCue
                                ? activeCue.text
                                : '';

                        if (subtitleText !== lastSubtitleText) {
                            subtitleBox.textContent =
                                subtitleText;

                            subtitleBox.style.opacity =
                                subtitleText ? '1' : '0';

                            lastSubtitleText = subtitleText;
                        }

                        progress.style.width =
                            (
                                Math.min(
                                    1,
                                    elapsed / duration
                                ) * 100
                            ).toFixed(3) + '%';

                        if (elapsed < duration) {
                            requestAnimationFrame(renderFrame);
                        }
                        else {
                            progress.style.width = '100%';
                            resolve();
                        }
                    };

                    requestAnimationFrame(renderFrame);
                });
            }
            """,
            animation_data,
        )

        video = page.video

        context.close()

        if video is None:
            browser.close()
            raise RuntimeError(
                "Playwright فایل ویدئو ایجاد نکرد."
            )

        video.save_as(str(output_path))
        browser.close()

    if not output_path.is_file():
        raise RuntimeError(
            f"فایل خروجی ساخته نشد: {output_path}"
        )

    print()
    print("=" * 68)
    print("ضبط ویدئو با موفقیت تمام شد.")
    print(f"فایل ویدئو: {output_path}")
    print(f"طرح صحنه‌ها: {SCENE_PLAN_PATH}")
    print("=" * 68)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print()
        print(f"خطا: {error}", file=sys.stderr)
        raise