from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import (
    QAudioOutput,
    QMediaDevices,
    QMediaPlayer,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .audio_processor import (
    AudioProcessingError,
    inspect_audio,
)
from .profile_store import VoiceProfileStore
from .recorder import AudioRecorder


class VoiceProfilesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("مدیریت صدای من")
        self.setMinimumSize(860, 560)
        self.resize(940, 620)
        self.setModal(True)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

        self.store = VoiceProfileStore()
        self.source_path: Path | None = None
        self.devices = QMediaDevices.audioInputs()

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)

        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_output)

        self.recorder = AudioRecorder(self)
        self.recorder.recording_started.connect(
            self._recording_started
        )
        self.recorder.recording_stopped.connect(
            self._recording_stopped
        )
        self.recorder.duration_changed.connect(
            self._recording_duration_changed
        )
        self.recorder.error_occurred.connect(
            self._recording_error
        )

        self._build_ui()
        self._load_profiles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        title = QLabel("🎙 مدیریت نمونه‌ها و پروفایل‌های صوتی")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        notice = QLabel(
            "نمونه‌ها فقط روی این رایانه نگهداری می‌شوند و "
            "در Git ثبت نخواهند شد. برای نتیجه بهتر، بین ۳۰ "
            "تا ۹۰ ثانیه در محیط آرام صحبت کنید."
        )
        notice.setWordWrap(True)
        root.addWidget(notice)

        content = QHBoxLayout()
        content.setSpacing(16)
        root.addLayout(content, 1)

        list_layout = QVBoxLayout()
        list_layout.addWidget(QLabel("پروفایل‌های ذخیره‌شده:"))

        self.profile_list = QListWidget()
        self.profile_list.currentItemChanged.connect(
            self._show_selected_profile
        )
        list_layout.addWidget(self.profile_list, 1)

        self.delete_button = QPushButton("حذف پروفایل")
        self.delete_button.clicked.connect(
            self._delete_profile
        )
        list_layout.addWidget(self.delete_button)

        content.addLayout(list_layout, 1)

        editor_layout = QVBoxLayout()
        editor_layout.setSpacing(12)
        content.addLayout(editor_layout, 2)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        editor_layout.addLayout(form)

        form.addWidget(QLabel("نام پروفایل:"), 0, 0)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(
            "برای مثال: صدای خودم"
        )
        form.addWidget(self.name_edit, 0, 1, 1, 2)

        form.addWidget(QLabel("میکروفن:"), 1, 0)
        self.microphone_combo = QComboBox()

        for device in self.devices:
            self.microphone_combo.addItem(
                device.description()
            )

        form.addWidget(
            self.microphone_combo,
            1,
            1,
            1,
            2,
        )

        recording_buttons = QHBoxLayout()

        self.record_button = QPushButton("● شروع ضبط")
        self.record_button.clicked.connect(
            self._start_recording
        )
        recording_buttons.addWidget(self.record_button)

        self.stop_button = QPushButton("■ توقف")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(
            self.recorder.stop
        )
        recording_buttons.addWidget(self.stop_button)

        self.duration_label = QLabel("۰۰:۰۰")
        self.duration_label.setObjectName("valueBadge")
        recording_buttons.addWidget(self.duration_label)

        form.addLayout(recording_buttons, 2, 0, 1, 3)

        file_buttons = QHBoxLayout()

        self.import_button = QPushButton("واردکردن فایل صوتی")
        self.import_button.clicked.connect(
            self._import_audio
        )
        file_buttons.addWidget(self.import_button)

        self.play_button = QPushButton("پخش نمونه")
        self.play_button.clicked.connect(
            self._play_source
        )
        self.play_button.setEnabled(False)
        file_buttons.addWidget(self.play_button)

        form.addLayout(file_buttons, 3, 0, 1, 3)

        self.source_label = QLabel(
            "هنوز نمونه‌ای ضبط یا انتخاب نشده است."
        )
        self.source_label.setWordWrap(True)
        self.source_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        editor_layout.addWidget(self.source_label)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        editor_layout.addWidget(self.info_label)

        self.consent_checkbox = QCheckBox(
            "تأیید می‌کنم این صدا متعلق به من است یا "
            "اجازه صریح استفاده از آن را دارم."
        )
        editor_layout.addWidget(self.consent_checkbox)

        self.save_button = QPushButton(
            "پردازش و ذخیره پروفایل"
        )
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(
            self._save_profile
        )
        editor_layout.addWidget(self.save_button)

        editor_layout.addStretch()

        close_button = QPushButton("بستن")
        close_button.clicked.connect(self.accept)
        root.addWidget(close_button)

        self.setStyleSheet(
            """
            QLineEdit {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 9px;
                min-height: 38px;
                padding: 0 12px;
            }
            QListWidget {
                background-color: #0f172a;
                color: #f8fafc;
                border: 1px solid #334155;
                border-radius: 10px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 9px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #4f46e5;
            }
            QCheckBox {
                spacing: 9px;
                color: #e2e8f0;
            }
            """
        )

    def _load_profiles(self) -> None:
        self.profile_list.clear()

        for profile in self.store.list_profiles():
            item = QListWidgetItem(profile.name)
            item.setData(
                Qt.ItemDataRole.UserRole,
                profile.profile_id,
            )
            item.setToolTip(str(profile.processed_path))
            self.profile_list.addItem(item)

        self.delete_button.setEnabled(
            self.profile_list.count() > 0
        )

    def _start_recording(self) -> None:
        if not self.devices:
            QMessageBox.warning(
                self,
                "میکروفن پیدا نشد",
                "هیچ ورودی صوتی در سیستم شناسایی نشد.",
            )
            return

        index = self.microphone_combo.currentIndex()

        if index < 0 or index >= len(self.devices):
            return

        output_path = self.store.create_staging_path()
        self.recorder.start(
            self.devices[index],
            output_path,
        )

    def _recording_started(self) -> None:
        self.record_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.duration_label.setText("۰۰:۰۰")
        self.source_label.setText(
            "در حال ضبط صدا… واضح و با فاصله مناسب صحبت کنید."
        )

    def _recording_duration_changed(
        self,
        milliseconds: int,
    ) -> None:
        seconds = max(0, milliseconds // 1000)
        minutes, seconds = divmod(seconds, 60)
        self.duration_label.setText(
            f"{minutes:02d}:{seconds:02d}"
        )

    def _recording_stopped(self, path_text: str) -> None:
        self.record_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        path = Path(path_text)

        if not path.exists() or path.stat().st_size == 0:
            QMessageBox.warning(
                self,
                "ضبط ناموفق",
                "فایل ضبط‌شده ساخته نشد یا خالی است.",
            )
            return

        self._set_source(path)

    def _recording_error(self, message: str) -> None:
        self.record_button.setEnabled(True)
        self.import_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        QMessageBox.critical(
            self,
            "خطای ضبط صدا",
            message,
        )

    def _import_audio(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب نمونه صدا",
            "",
            (
                "فایل‌های صوتی "
                "(*.wav *.mp3 *.m4a *.aac *.flac *.ogg *.wma);;"
                "همه فایل‌ها (*.*)"
            ),
        )

        if file_name:
            self._set_source(Path(file_name))

    def _set_source(self, path: Path) -> None:
        try:
            metadata = inspect_audio(path)
        except AudioProcessingError as exc:
            QMessageBox.critical(
                self,
                "فایل صوتی نامعتبر",
                str(exc),
            )
            return

        self.source_path = path.resolve()
        self.play_button.setEnabled(True)

        duration = float(metadata["duration"])
        minutes, seconds = divmod(int(duration), 60)

        self.source_label.setText(
            f"نمونه انتخاب‌شده:\n{self.source_path}"
        )
        self.info_label.setText(
            f"مدت: {minutes:02d}:{seconds:02d} | "
            f"کدک: {metadata['codec']} | "
            f"نرخ نمونه‌برداری: "
            f"{metadata['sample_rate']:,} Hz | "
            f"کانال: {metadata['channels']}"
        )

    def _play_source(self) -> None:
        if self.source_path is None:
            return

        if not self.source_path.exists():
            QMessageBox.warning(
                self,
                "فایل پیدا نشد",
                str(self.source_path),
            )
            return

        self.player.stop()
        self.player.setSource(
            QUrl.fromLocalFile(
                str(self.source_path.resolve())
            )
        )
        self.player.play()

    def _save_profile(self) -> None:
        if self.source_path is None:
            QMessageBox.warning(
                self,
                "نمونه صدا انتخاب نشده است",
                "ابتدا صدا ضبط کنید یا یک فایل صوتی وارد کنید.",
            )
            return

        self.save_button.setEnabled(False)
        self.save_button.setText("در حال پردازش…")

        try:
            profile = self.store.create_profile(
                name=self.name_edit.text(),
                source_path=self.source_path,
                consent=self.consent_checkbox.isChecked(),
            )
        except (
            ValueError,
            OSError,
            AudioProcessingError,
        ) as exc:
            QMessageBox.critical(
                self,
                "ذخیره پروفایل ناموفق بود",
                str(exc),
            )
        else:
            QMessageBox.information(
                self,
                "پروفایل ذخیره شد",
                "نمونه صدا با مشخصات زیر ذخیره شد:\n\n"
                "WAV / PCM 16-bit\n"
                "Mono\n"
                "24000 Hz\n\n"
                f"{profile.processed_path}",
            )

            self.name_edit.clear()
            self.consent_checkbox.setChecked(False)
            self.source_path = profile.processed_path
            self._set_source(profile.processed_path)
            self._load_profiles()
        finally:
            self.save_button.setEnabled(True)
            self.save_button.setText(
                "پردازش و ذخیره پروفایل"
            )

    def _show_selected_profile(
        self,
        current,
        previous=None,
    ) -> None:
        if current is None:
            return

        profile_id = current.data(
            Qt.ItemDataRole.UserRole
        )

        profile = next(
            (
                item
                for item in self.store.list_profiles()
                if item.profile_id == profile_id
            ),
            None,
        )

        if profile is None:
            return

        self.name_edit.setText(profile.name)
        self._set_source(profile.processed_path)

    def _delete_profile(self) -> None:
        current = self.profile_list.currentItem()

        if current is None:
            return

        profile_id = current.data(
            Qt.ItemDataRole.UserRole
        )
        profile_name = current.text()

        answer = QMessageBox.question(
            self,
            "حذف پروفایل صدا",
            f"پروفایل «{profile_name}» و تمام فایل‌های آن حذف شود؟",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.player.stop()
            self.store.delete_profile(profile_id)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "حذف ناموفق بود",
                str(exc),
            )
            return

        self.source_path = None
        self.source_label.setText(
            "هنوز نمونه‌ای ضبط یا انتخاب نشده است."
        )
        self.info_label.clear()
        self.play_button.setEnabled(False)
        self.name_edit.clear()
        self._load_profiles()

    def reject(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()

        self.player.stop()
        super().reject()

    def accept(self) -> None:
        if self.recorder.is_recording:
            self.recorder.stop()

        self.player.stop()
        super().accept()
