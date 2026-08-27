from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(slots=True)
class SubtitleCue:
    """Represents one subtitle cue with millisecond timing."""

    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)

    def clone(self, **changes) -> "SubtitleCue":
        return replace(self, **changes)

    def normalized(self) -> "SubtitleCue":
        normalized_text = (
            str(self.text)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
            .strip()
        )

        return SubtitleCue(
            index=max(1, int(self.index)),
            start_ms=max(0, int(self.start_ms)),
            end_ms=max(0, int(self.end_ms)),
            text=normalized_text,
        )

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.index < 1:
            errors.append("شماره زیرنویس باید بزرگ‌تر از صفر باشد.")

        if self.start_ms < 0:
            errors.append("زمان شروع نمی‌تواند منفی باشد.")

        if self.end_ms <= self.start_ms:
            errors.append(
                "زمان پایان باید بزرگ‌تر از زمان شروع باشد."
            )

        if not self.text.strip():
            errors.append("متن زیرنویس خالی است.")

        return errors
