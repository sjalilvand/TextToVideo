from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .audio_processor import process_voice_sample


PROJECT_ROOT = Path(__file__).resolve().parents[3]
VOICE_PROFILES_DIR = PROJECT_ROOT / "voice-profiles"
STAGING_DIR = VOICE_PROFILES_DIR / ".staging"


@dataclass(frozen=True)
class VoiceProfile:
    profile_id: str
    name: str
    directory: Path
    original_path: Path
    processed_path: Path
    created_at: str
    audio: dict[str, Any]

    @property
    def duration(self) -> float:
        return float(self.audio.get("duration", 0))


class VoiceProfileStore:
    def __init__(self):
        VOICE_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
        STAGING_DIR.mkdir(parents=True, exist_ok=True)

    def list_profiles(self) -> list[VoiceProfile]:
        profiles: list[VoiceProfile] = []

        for metadata_path in VOICE_PROFILES_DIR.glob(
            "*/profile.json"
        ):
            try:
                profile = self._load_metadata(metadata_path)
            except (OSError, ValueError, KeyError, TypeError):
                continue

            if profile.processed_path.exists():
                profiles.append(profile)

        return sorted(
            profiles,
            key=lambda item: item.created_at,
            reverse=True,
        )

    def create_profile(
        self,
        name: str,
        source_path: Path,
        consent: bool,
    ) -> VoiceProfile:
        name = name.strip()

        if not name:
            raise ValueError("نام پروفایل صدا را وارد کنید.")

        if not consent:
            raise ValueError(
                "تأیید مالکیت یا اجازه استفاده از صدا الزامی است."
            )

        source_path = source_path.resolve()

        if not source_path.exists():
            raise ValueError("فایل نمونه صدا پیدا نشد.")

        profile_id = uuid.uuid4().hex[:12]
        profile_directory = VOICE_PROFILES_DIR / profile_id
        profile_directory.mkdir(parents=True, exist_ok=False)

        suffix = source_path.suffix.lower() or ".wav"
        original_path = profile_directory / f"original{suffix}"
        processed_path = profile_directory / "sample.wav"

        try:
            shutil.copy2(source_path, original_path)
            audio = process_voice_sample(
                original_path,
                processed_path,
            )

            created_at = datetime.now(
                timezone.utc
            ).isoformat()

            metadata = {
                "version": 1,
                "profile_id": profile_id,
                "name": name,
                "created_at": created_at,
                "consent_confirmed": True,
                "original_file": original_path.name,
                "processed_file": processed_path.name,
                "audio": audio,
            }

            metadata_path = profile_directory / "profile.json"
            metadata_path.write_text(
                json.dumps(
                    metadata,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            shutil.rmtree(
                profile_directory,
                ignore_errors=True,
            )
            raise

        return self._load_metadata(metadata_path)

    def delete_profile(self, profile_id: str) -> None:
        profile_id = profile_id.strip()

        if (
            not profile_id
            or "/" in profile_id
            or "\\" in profile_id
            or profile_id.startswith(".")
        ):
            raise ValueError("شناسه پروفایل معتبر نیست.")

        profile_directory = VOICE_PROFILES_DIR / profile_id

        if profile_directory.exists():
            shutil.rmtree(profile_directory)

    def create_staging_path(self) -> Path:
        STAGING_DIR.mkdir(parents=True, exist_ok=True)
        return STAGING_DIR / (
            "recording-"
            + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            + ".wav"
        )

    def _load_metadata(
        self,
        metadata_path: Path,
    ) -> VoiceProfile:
        payload = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        directory = metadata_path.parent

        return VoiceProfile(
            profile_id=str(payload["profile_id"]),
            name=str(payload["name"]),
            directory=directory,
            original_path=directory / payload["original_file"],
            processed_path=directory / payload["processed_file"],
            created_at=str(payload["created_at"]),
            audio=dict(payload.get("audio") or {}),
        )
