from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.features.subtitles import SrtService


def main() -> int:
    source_path = (
        PROJECT_ROOT
        / "output"
        / "narration-generated.srt"
    )

    output_path = (
        PROJECT_ROOT
        / "output"
        / "narration-generated.edited-test.srt"
    )

    print("=" * 70)
    print("Subtitle core test")
    print("=" * 70)
    print(f"Source: {source_path}")

    cues = SrtService.load(source_path)

    print(f"Subtitle count: {len(cues)}")

    if not cues:
        raise RuntimeError(
            "فایل زیرنویس هیچ ردیفی ندارد."
        )

    duration_ms = max(cue.end_ms for cue in cues)

    print(
        "Timeline end: "
        f"{SrtService.ms_to_timestamp(duration_ms)}"
    )

    print("-" * 70)
    print("First subtitle:")
    print(
        f"{SrtService.ms_to_timestamp(cues[0].start_ms)}"
        " --> "
        f"{SrtService.ms_to_timestamp(cues[0].end_ms)}"
    )
    print(cues[0].text)

    print("-" * 70)
    print("Last subtitle:")
    print(
        f"{SrtService.ms_to_timestamp(cues[-1].start_ms)}"
        " --> "
        f"{SrtService.ms_to_timestamp(cues[-1].end_ms)}"
    )
    print(cues[-1].text)

    warnings = SrtService.validate_timeline(cues)

    print("-" * 70)
    print(f"Timeline warning count: {len(warnings)}")

    for warning in warnings[:10]:
        print(f"- {warning}")

    if len(warnings) > 10:
        print(
            f"... and {len(warnings) - 10} more warnings"
        )

    SrtService.save(output_path, cues)

    reloaded_cues = SrtService.load(output_path)

    if len(reloaded_cues) != len(cues):
        raise RuntimeError(
            "تعداد زیرنویس‌ها پس از ذخیره تغییر کرده است."
        )

    for original, reloaded in zip(cues, reloaded_cues):
        if (
            original.start_ms != reloaded.start_ms
            or original.end_ms != reloaded.end_ms
            or original.text != reloaded.text
        ):
            raise RuntimeError(
                "محتوای فایل پس از ذخیره تغییر کرده است."
            )

    print("-" * 70)
    print("Save and reload test: OK")
    print(f"Test output: {output_path}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
