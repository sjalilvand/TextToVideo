from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import (
    QAudioInput,
    QMediaCaptureSession,
    QMediaFormat,
    QMediaRecorder,
)


class AudioRecorder(QObject):
    recording_started = Signal()
    recording_stopped = Signal(str)
    duration_changed = Signal(int)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)

        self.capture_session = QMediaCaptureSession(self)
        self.audio_input = QAudioInput(self)
        self.recorder = QMediaRecorder(self)

        self.capture_session.setAudioInput(self.audio_input)
        self.capture_session.setRecorder(self.recorder)

        media_format = QMediaFormat()
        media_format.setFileFormat(
            QMediaFormat.FileFormat.Wave
        )
        media_format.setAudioCodec(
            QMediaFormat.AudioCodec.Wave
        )

        self.recorder.setMediaFormat(media_format)
        self.recorder.setAudioSampleRate(48000)
        self.recorder.setAudioChannelCount(1)
        self.recorder.setQuality(
            QMediaRecorder.Quality.HighQuality
        )

        self._output_path: Path | None = None
        self._stop_requested = False

        self.recorder.durationChanged.connect(
            self._on_duration_changed
        )
        self.recorder.recorderStateChanged.connect(
            self._on_state_changed
        )
        self.recorder.errorOccurred.connect(
            self._on_error
        )

    @property
    def is_recording(self) -> bool:
        return (
            self.recorder.recorderState()
            == QMediaRecorder.RecorderState.RecordingState
        )

    def start(self, device, output_path: Path) -> None:
        if self.is_recording:
            return

        output_path = output_path.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.unlink(missing_ok=True)

        self._output_path = output_path
        self._stop_requested = False

        self.audio_input.setDevice(device)
        self.recorder.setOutputLocation(
            QUrl.fromLocalFile(str(output_path))
        )
        self.recorder.record()

    def stop(self) -> None:
        if self.is_recording:
            self._stop_requested = True
            self.recorder.stop()

    def _on_duration_changed(
        self,
        milliseconds: int,
    ) -> None:
        # سیگنال اصلی Qt از نوع qlonglong است. ارسال آن از
        # طریق یک متد پایتونی، ناسازگاری اتصال مستقیم آن با
        # Signal(int) را در PySide6 6.11 برطرف می‌کند.
        self.duration_changed.emit(int(milliseconds))

    def _on_state_changed(self, state) -> None:
        if (
            state
            == QMediaRecorder.RecorderState.RecordingState
        ):
            self.recording_started.emit()
            return

        if (
            state
            == QMediaRecorder.RecorderState.StoppedState
            and self._stop_requested
            and self._output_path is not None
        ):
            self._stop_requested = False
            QTimer.singleShot(600, self._emit_stopped)

    def _emit_stopped(self) -> None:
        if self._output_path is None:
            return

        actual_url = self.recorder.actualLocation()

        if actual_url.isLocalFile():
            actual_path = Path(actual_url.toLocalFile())
        else:
            actual_path = self._output_path

        self.recording_stopped.emit(str(actual_path))

    def _on_error(self, error, message: str) -> None:
        if error == QMediaRecorder.Error.NoError:
            return

        self._stop_requested = False
        self.error_occurred.emit(
            message or f"خطای ضبط صدا: {error.name}"
        )
