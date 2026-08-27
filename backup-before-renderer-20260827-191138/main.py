from __future__ import annotations

import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.tts_worker import TTSWorker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TEMP_DIR = PROJECT_ROOT / "temp" / "gui-projects"

SUPPORTED_TEXT_EXTENSIONS = {".txt", ".html", ".htm"}
SUPPORTED_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp"
}


class SectionTitle(QWidget):
    def __init__(self, title: str, description: str):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 14)
        layout.setSpacing(5)

        title_label = QLabel(title)
        title_label.setObjectName("pageTitle")

        description_label = QLabel(description)
        description_label.setObjectName("pageDescription")
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)


class Card(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setFrameShape(QFrame.Shape.NoFrame)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.current_text_file: Path | None = None
        self.current_image_file: Path | None = None

        self.tts_worker: TTSWorker | None = None
        self.generated_audio_path: Path | None = None
        self.generated_srt_path: Path | None = None
        self.generated_timing_path: Path | None = None

        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.85)

        self.media_player = QMediaPlayer(self)
        self.media_player.setAudioOutput(self.audio_output)

        self.setWindowTitle("استودیو متن به ویدئو")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 820)
        self.setAcceptDrops(True)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        TEMP_DIR.mkdir(parents=True, exist_ok=True)

        self.build_ui()
        self.apply_style()
        self.update_text_statistics()

    def build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(18, 18, 18, 14)
        root_layout.setSpacing(14)

        root_layout.addWidget(self.create_header())

        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(220)
        self.navigation.setSpacing(6)

        navigation_items = [
            "۱   محتوا",
            "۲   صدا",
            "۳   زیرنویس",
            "۴   تصویر و قالب",
            "۵   ساخت خروجی",
        ]

        for text in navigation_items:
            item = QListWidgetItem(text)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight |
                Qt.AlignmentFlag.AlignVCenter
            )
            item.setSizeHint(item.sizeHint().expandedTo(
                self.navigation.sizeHint()
            ))
            self.navigation.addItem(item)

        self.pages = QStackedWidget()
        self.pages.setObjectName("pages")

        self.pages.addWidget(self.create_content_page())
        self.pages.addWidget(self.create_voice_page())
        self.pages.addWidget(self.create_subtitle_page())
        self.pages.addWidget(self.create_image_page())
        self.pages.addWidget(self.create_output_page())

        self.navigation.currentRowChanged.connect(
            self.pages.setCurrentIndex
        )
        self.navigation.currentRowChanged.connect(
            self.on_page_changed
        )
        self.navigation.setCurrentRow(0)

        body_layout.addWidget(self.navigation)
        body_layout.addWidget(self.pages, 1)

        root_layout.addLayout(body_layout, 1)
        root_layout.addWidget(self.create_status_bar())

    def create_header(self):
        header = QFrame()
        header.setObjectName("header")

        layout = QHBoxLayout(header)
        layout.setContentsMargins(22, 15, 22, 15)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)

        title = QLabel("استودیو متن به ویدئو")
        title.setObjectName("appTitle")

        subtitle = QLabel(
            "تبدیل متن فارسی به صوت، زیرنویس و ویدئوی حرفه‌ای"
        )
        subtitle.setObjectName("appSubtitle")

        text_layout.addWidget(title)
        text_layout.addWidget(subtitle)

        badge = QLabel("نسخه آزمایشی ۱.۰")
        badge.setObjectName("versionBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(125, 34)

        layout.addLayout(text_layout)
        layout.addStretch()
        layout.addWidget(badge)

        return header

    def create_content_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        layout.addWidget(
            SectionTitle(
                "انتخاب و ویرایش محتوا",
                "یک فایل متنی یا HTML انتخاب کنید. "
                "متن استخراج‌شده قبل از تبدیل به صوت قابل ویرایش است."
            )
        )

        file_card = Card()
        file_layout = QHBoxLayout(file_card)
        file_layout.setContentsMargins(18, 16, 18, 16)

        self.file_path_label = QLabel(
            "هنوز فایلی انتخاب نشده است؛ فایل را اینجا رها کنید."
        )
        self.file_path_label.setObjectName("pathLabel")
        self.file_path_label.setWordWrap(True)

        open_button = QPushButton("انتخاب فایل TXT یا HTML")
        open_button.setObjectName("primaryButton")
        open_button.clicked.connect(self.choose_text_file)

        clear_button = QPushButton("پاک‌کردن")
        clear_button.clicked.connect(self.clear_text)

        file_layout.addWidget(self.file_path_label, 1)
        file_layout.addWidget(clear_button)
        file_layout.addWidget(open_button)

        editor_card = Card()
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(10)

        editor_header = QHBoxLayout()

        editor_label = QLabel("متن آماده برای گویندگی")
        editor_label.setObjectName("cardTitle")

        self.statistics_label = QLabel()
        self.statistics_label.setObjectName("statistics")

        editor_header.addWidget(editor_label)
        editor_header.addStretch()
        editor_header.addWidget(self.statistics_label)

        self.text_editor = QPlainTextEdit()
        self.text_editor.setObjectName("textEditor")
        self.text_editor.setPlaceholderText(
            "متن فارسی را مستقیماً اینجا بنویسید، "
            "یا یک فایل TXT/HTML انتخاب کنید..."
        )
        self.text_editor.setLayoutDirection(
            Qt.LayoutDirection.RightToLeft
        )

        text_option = (
            self.text_editor.document().defaultTextOption()
        )
        text_option.setTextDirection(
            Qt.LayoutDirection.RightToLeft
        )
        text_option.setAlignment(
            Qt.AlignmentFlag.AlignRight
        )
        self.text_editor.document().setDefaultTextOption(
            text_option
        )

        self.text_editor.textChanged.connect(
            self.update_text_statistics
        )

        editor_layout.addLayout(editor_header)
        editor_layout.addWidget(self.text_editor, 1)

        next_button = QPushButton("مرحله بعد: تنظیم صدا")
        next_button.setObjectName("primaryButton")
        next_button.clicked.connect(lambda: self.go_to_page(1))

        button_layout = QHBoxLayout()
        button_layout.addStretch()
        button_layout.addWidget(next_button)

        layout.addWidget(file_card)
        layout.addWidget(editor_card, 1)
        layout.addLayout(button_layout)

        return page

    def create_voice_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        layout.addWidget(
            SectionTitle(
                "تنظیم صدای گوینده",
                "صدای فارسی، سرعت و زیر و بمی گفتار را تنظیم کنید."
            )
        )

        card = Card()
        form = QGridLayout(card)
        form.setContentsMargins(24, 22, 24, 22)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(18)

        voice_label = QLabel("صدای فارسی:")
        self.voice_combo = QComboBox()
        self.voice_combo.addItem(
            "دیلارا — صدای زن فارسی",
            "fa-IR-DilaraNeural"
        )
        self.voice_combo.addItem(
            "فرید — صدای مرد فارسی",
            "fa-IR-FaridNeural"
        )

        speed_label = QLabel("سرعت گویندگی:")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(-50, 50)
        self.speed_slider.setValue(0)

        self.speed_value = QLabel("۰٪")
        self.speed_value.setObjectName("valueBadge")
        self.speed_slider.valueChanged.connect(
            lambda value: self.speed_value.setText(
                f"{value:+d}٪".replace("+0", "0")
            )
        )

        pitch_label = QLabel("زیر و بمی صدا:")
        self.pitch_slider = QSlider(Qt.Orientation.Horizontal)
        self.pitch_slider.setRange(-50, 50)
        self.pitch_slider.setValue(0)

        self.pitch_value = QLabel("۰ هرتز")
        self.pitch_value.setObjectName("valueBadge")
        self.pitch_slider.valueChanged.connect(
            lambda value: self.pitch_value.setText(
                f"{value:+d} هرتز".replace("+0", "0")
            )
        )

        self.sample_button = QPushButton("شنیدن نمونه صدا")
        self.sample_button.clicked.connect(
            self.generate_voice_sample
        )

        self.generate_audio_button = QPushButton(
            "تولید کامل MP3 و زیرنویس SRT"
        )
        self.generate_audio_button.setObjectName(
            "primaryButton"
        )
        self.generate_audio_button.clicked.connect(
            self.generate_full_audio
        )

        form.addWidget(voice_label, 0, 0)
        form.addWidget(self.voice_combo, 0, 1, 1, 2)

        form.addWidget(speed_label, 1, 0)
        form.addWidget(self.speed_slider, 1, 1)
        form.addWidget(self.speed_value, 1, 2)

        form.addWidget(pitch_label, 2, 0)
        form.addWidget(self.pitch_slider, 2, 1)
        form.addWidget(self.pitch_value, 2, 2)

        form.addWidget(self.sample_button, 3, 1)
        form.addWidget(self.generate_audio_button, 3, 2)

        form.setColumnStretch(1, 1)

        buttons = self.create_page_buttons(0, 2)

        layout.addWidget(card)
        layout.addStretch()
        layout.addLayout(buttons)

        return page

    def create_subtitle_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        layout.addWidget(
            SectionTitle(
                "طراحی زیرنویس فارسی",
                "ظاهر، اندازه، موقعیت و تعداد کلمات هر بخش "
                "از زیرنویس را مشخص کنید."
            )
        )

        card = Card()
        form = QGridLayout(card)
        form.setContentsMargins(24, 22, 24, 22)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(18)

        words_label = QLabel("حداکثر کلمه در هر زیرنویس:")
        self.words_spin = QSpinBox()
        self.words_spin.setRange(3, 20)
        self.words_spin.setValue(8)

        font_label = QLabel("فونت:")
        self.font_combo = QComboBox()
        self.font_combo.addItems([
            "Tahoma",
            "Vazirmatn",
            "B Nazanin",
            "Segoe UI",
        ])

        size_label = QLabel("اندازه فونت:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(24, 100)
        self.font_size_spin.setValue(54)

        position_label = QLabel("محل زیرنویس:")
        self.subtitle_position = QComboBox()
        self.subtitle_position.addItems([
            "پایین تصویر",
            "مرکز تصویر",
            "بالای تصویر",
        ])

        preview = QLabel("این یک نمونه زیرنویس فارسی است")
        preview.setObjectName("subtitlePreview")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(110)

        form.addWidget(words_label, 0, 0)
        form.addWidget(self.words_spin, 0, 1)
        form.addWidget(font_label, 1, 0)
        form.addWidget(self.font_combo, 1, 1)
        form.addWidget(size_label, 2, 0)
        form.addWidget(self.font_size_spin, 2, 1)
        form.addWidget(position_label, 3, 0)
        form.addWidget(self.subtitle_position, 3, 1)
        form.addWidget(preview, 4, 0, 1, 2)

        form.setColumnStretch(1, 1)

        layout.addWidget(card)
        layout.addStretch()
        layout.addLayout(self.create_page_buttons(1, 3))

        return page

    def create_image_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        layout.addWidget(
            SectionTitle(
                "انتخاب تصویر و قالب ویدئو",
                "تصویر پس‌زمینه و نسبت تصویر خروجی را تعیین کنید."
            )
        )

        content_layout = QHBoxLayout()
        content_layout.setSpacing(12)

        settings_card = Card()
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(14)

        image_button = QPushButton("انتخاب تصویر پس‌زمینه")
        image_button.setObjectName("primaryButton")
        image_button.clicked.connect(self.choose_image)

        self.image_path_label = QLabel(
            "هنوز تصویری انتخاب نشده است."
        )
        self.image_path_label.setObjectName("pathLabel")
        self.image_path_label.setWordWrap(True)

        format_label = QLabel("قالب ویدئو")
        format_label.setObjectName("cardTitle")

        self.vertical_radio = QRadioButton(
            "عمودی — 1080 × 1920 (اینستاگرام)"
        )
        horizontal_radio = QRadioButton(
            "افقی — 1920 × 1080 (یوتیوب)"
        )
        square_radio = QRadioButton(
            "مربعی — 1080 × 1080"
        )

        self.format_group = QButtonGroup(self)
        self.format_group.addButton(self.vertical_radio, 0)
        self.format_group.addButton(horizontal_radio, 1)
        self.format_group.addButton(square_radio, 2)

        self.vertical_radio.setChecked(True)

        display_label = QLabel("نحوه نمایش تصویر")
        display_label.setObjectName("cardTitle")

        self.image_mode_combo = QComboBox()
        self.image_mode_combo.addItems([
            "پوشاندن کامل قاب",
            "نمایش کامل تصویر",
            "پس‌زمینه محو",
            "حرکت و زوم آهسته",
        ])

        settings_layout.addWidget(image_button)
        settings_layout.addWidget(self.image_path_label)
        settings_layout.addSpacing(8)
        settings_layout.addWidget(format_label)
        settings_layout.addWidget(self.vertical_radio)
        settings_layout.addWidget(horizontal_radio)
        settings_layout.addWidget(square_radio)
        settings_layout.addSpacing(8)
        settings_layout.addWidget(display_label)
        settings_layout.addWidget(self.image_mode_combo)
        settings_layout.addStretch()

        preview_card = Card()
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 16, 16, 16)

        preview_title = QLabel("پیش‌نمایش تصویر")
        preview_title.setObjectName("cardTitle")

        self.image_preview = QLabel(
            "تصویر انتخاب‌شده\nدر این قسمت نمایش داده می‌شود"
        )
        self.image_preview.setObjectName("imagePreview")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setMinimumSize(310, 390)

        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.image_preview, 1)

        content_layout.addWidget(settings_card, 1)
        content_layout.addWidget(preview_card, 1)

        layout.addLayout(content_layout, 1)
        layout.addLayout(self.create_page_buttons(2, 4))

        return page

    def create_output_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(12)

        layout.addWidget(
            SectionTitle(
                "ساخت خروجی نهایی",
                "پس از بررسی تنظیمات، ابتدا پیش‌نمایش کوتاه "
                "و سپس ویدئوی کامل را تولید کنید."
            )
        )

        summary_card = Card()
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(24, 22, 24, 22)
        summary_layout.setSpacing(14)

        summary_title = QLabel("خلاصه پروژه")
        summary_title.setObjectName("cardTitle")

        self.summary_label = QLabel()
        self.summary_label.setObjectName("summary")
        self.summary_label.setWordWrap(True)

        self.preview_button = QPushButton(
            "ساخت پیش‌نمایش ۱۵ ثانیه‌ای"
        )
        self.preview_button.clicked.connect(
            self.show_upcoming_message
        )

        self.render_button = QPushButton("ساخت ویدئوی نهایی")
        self.render_button.setObjectName("renderButton")
        self.render_button.clicked.connect(
            self.show_upcoming_message
        )

        output_buttons = QHBoxLayout()
        output_buttons.addWidget(self.preview_button)
        output_buttons.addWidget(self.render_button)

        summary_layout.addWidget(summary_title)
        summary_layout.addWidget(self.summary_label)
        summary_layout.addSpacing(8)
        summary_layout.addLayout(output_buttons)

        layout.addWidget(summary_card)
        layout.addStretch()
        layout.addLayout(self.create_page_buttons(3, None))

        return page

    def create_page_buttons(
        self,
        previous_index: int | None,
        next_index: int | None
    ):
        layout = QHBoxLayout()

        if previous_index is not None:
            previous_button = QPushButton("مرحله قبل")
            previous_button.clicked.connect(
                lambda checked=False, index=previous_index:
                self.go_to_page(index)
            )
            layout.addWidget(previous_button)

        layout.addStretch()

        if next_index is not None:
            next_button = QPushButton("مرحله بعد")
            next_button.setObjectName("primaryButton")
            next_button.clicked.connect(
                lambda checked=False, index=next_index:
                self.go_to_page(index)
            )
            layout.addWidget(next_button)

        return layout

    def create_status_bar(self):
        status_frame = QFrame()
        status_frame.setObjectName("statusFrame")

        layout = QHBoxLayout(status_frame)
        layout.setContentsMargins(14, 9, 14, 9)

        self.status_label = QLabel("وضعیت: آماده")
        self.status_label.setObjectName("statusLabel")

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedWidth(260)

        layout.addWidget(self.status_label)
        layout.addStretch()
        layout.addWidget(self.progress_bar)

        return status_frame

    def choose_text_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب فایل محتوا",
            str(PROJECT_ROOT / "input"),
            "فایل‌های محتوا (*.txt *.html *.htm);;"
            "فایل متنی (*.txt);;"
            "فایل HTML (*.html *.htm)"
        )

        if filename:
            self.load_text_file(Path(filename))

    def load_text_file(self, file_path: Path):
        if file_path.suffix.lower() not in SUPPORTED_TEXT_EXTENSIONS:
            QMessageBox.warning(
                self,
                "فرمت پشتیبانی نمی‌شود",
                "فقط فایل‌های TXT، HTML و HTM قابل استفاده هستند."
            )
            return

        try:
            raw_content = self.read_text_safely(file_path)

            if file_path.suffix.lower() in {".html", ".htm"}:
                extracted_text = self.extract_text_from_html(raw_content)
            else:
                extracted_text = self.normalize_text(raw_content)

            if not extracted_text.strip():
                raise ValueError(
                    "پس از پردازش، هیچ متن قابل استفاده‌ای پیدا نشد."
                )

            self.current_text_file = file_path
            self.file_path_label.setText(str(file_path))
            self.text_editor.setPlainText(extracted_text)

            self.status_label.setText(
                f"وضعیت: فایل «{file_path.name}» بارگذاری شد"
            )
            self.progress_bar.setValue(20)

        except Exception as error:
            QMessageBox.critical(
                self,
                "خطا در خواندن فایل",
                f"فایل قابل پردازش نبود:\n\n{error}"
            )

    @staticmethod
    def read_text_safely(file_path: Path) -> str:
        encodings = (
            "utf-8-sig",
            "utf-8",
            "cp1256",
            "windows-1252",
        )

        last_error = None

        for encoding in encodings:
            try:
                return file_path.read_text(encoding=encoding)
            except UnicodeDecodeError as error:
                last_error = error

        raise ValueError(
            f"رمزگذاری فایل شناسایی نشد: {last_error}"
        )

    @staticmethod
    def extract_text_from_html(html: str) -> str:
        soup = BeautifulSoup(html, "lxml")

        for tag in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "canvas",
            "form",
            "nav",
        ]):
            tag.decompose()

        preferred_container = (
            soup.find("main")
            or soup.find("article")
            or soup.body
            or soup
        )

        text = preferred_container.get_text(separator="\n")
        return MainWindow.normalize_text(text)

    @staticmethod
    def normalize_text(text: str) -> str:
        text = text.replace("\u200c", "\u200c")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r" *\n *", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def update_text_statistics(self):
        text = self.text_editor.toPlainText().strip()

        words = re.findall(r"\S+", text)
        paragraphs = [
            paragraph
            for paragraph in re.split(r"\n\s*\n|\n", text)
            if paragraph.strip()
        ]

        self.statistics_label.setText(
            f"{len(words):,} کلمه  •  "
            f"{len(paragraphs):,} بند  •  "
            f"{len(text):,} نویسه"
        )

    def clear_text(self):
        if not self.text_editor.toPlainText().strip():
            return

        result = QMessageBox.question(
            self,
            "پاک‌کردن متن",
            "آیا متن فعلی پاک شود؟",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes:
            self.current_text_file = None
            self.text_editor.clear()
            self.file_path_label.setText(
                "هنوز فایلی انتخاب نشده است؛ "
                "فایل را اینجا رها کنید."
            )
            self.progress_bar.setValue(0)
            self.status_label.setText("وضعیت: آماده")

    def choose_image(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب تصویر پس‌زمینه",
            str(PROJECT_ROOT / "input"),
            "فایل‌های تصویر (*.png *.jpg *.jpeg *.webp *.bmp)"
        )

        if not filename:
            return

        file_path = Path(filename)
        pixmap = QPixmap(str(file_path))

        if pixmap.isNull():
            QMessageBox.warning(
                self,
                "خطای تصویر",
                "تصویر انتخاب‌شده قابل نمایش نیست."
            )
            return

        self.current_image_file = file_path
        self.image_path_label.setText(str(file_path))

        scaled = pixmap.scaled(
            self.image_preview.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        self.image_preview.setPixmap(scaled)
        self.status_label.setText(
            f"وضعیت: تصویر «{file_path.name}» انتخاب شد"
        )
        self.progress_bar.setValue(max(
            self.progress_bar.value(),
            35
        ))

    def go_to_page(self, index: int):
        if index > 0 and not self.text_editor.toPlainText().strip():
            QMessageBox.warning(
                self,
                "متن وارد نشده است",
                "ابتدا یک فایل انتخاب کنید یا متن را در کادر بنویسید."
            )
            self.navigation.setCurrentRow(0)
            return

        self.navigation.setCurrentRow(index)

    def on_page_changed(self, index: int):
        progress_values = [20, 35, 50, 65, 80]

        if self.text_editor.toPlainText().strip():
            self.progress_bar.setValue(progress_values[index])

        if index == 4:
            self.update_summary()

    def update_summary(self):
        text = self.text_editor.toPlainText().strip()
        word_count = len(re.findall(r"\S+", text))

        voice = self.voice_combo.currentText()
        image = (
            self.current_image_file.name
            if self.current_image_file
            else "انتخاب نشده"
        )

        format_id = self.format_group.checkedId()
        formats = {
            0: "عمودی 1080×1920",
            1: "افقی 1920×1080",
            2: "مربعی 1080×1080",
        }

        self.summary_label.setText(
            f"تعداد کلمات: {word_count:,}\n"
            f"صدای انتخابی: {voice}\n"
            f"تصویر پس‌زمینه: {image}\n"
            f"قالب ویدئو: {formats.get(format_id, 'عمودی')}\n"
            f"پوشه خروجی: {OUTPUT_DIR}"
        )

    def generate_voice_sample(self):
        text = self.text_editor.toPlainText().strip()

        if not text:
            QMessageBox.warning(
                self,
                "متن وارد نشده است",
                "ابتدا متن موردنظر را وارد یا بارگذاری کنید."
            )
            return

        sample_text = text[:450]

        if len(text) > 450:
            last_separator = max(
                sample_text.rfind("."),
                sample_text.rfind("؟"),
                sample_text.rfind("!"),
                sample_text.rfind("\n"),
            )

            if last_separator >= 100:
                sample_text = sample_text[:last_separator + 1]

        self.start_tts_process(
            text=sample_text,
            output_directory=TEMP_DIR,
            output_stem="voice-sample",
            mode="sample",
        )

    def generate_full_audio(self):
        text = self.text_editor.toPlainText().strip()

        if not text:
            QMessageBox.warning(
                self,
                "متن وارد نشده است",
                "ابتدا متن موردنظر را وارد یا بارگذاری کنید."
            )
            return

        self.start_tts_process(
            text=text,
            output_directory=OUTPUT_DIR,
            output_stem="narration-generated",
            mode="full",
        )

    def start_tts_process(
        self,
        text: str,
        output_directory: Path,
        output_stem: str,
        mode: str,
    ):
        if (
            self.tts_worker is not None
            and self.tts_worker.isRunning()
        ):
            QMessageBox.information(
                self,
                "پردازش در حال اجرا است",
                "لطفاً تا پایان پردازش فعلی منتظر بمانید."
            )
            return

        voice = self.voice_combo.currentData()
        rate = self.speed_slider.value()
        pitch = self.pitch_slider.value()
        max_words = self.words_spin.value()

        self.sample_button.setEnabled(False)
        self.generate_audio_button.setEnabled(False)

        self.progress_bar.setValue(1)
        self.status_label.setText(
            "وضعیت: آماده‌سازی موتور Edge-TTS..."
        )

        self.tts_worker = TTSWorker(
            text=text,
            voice=voice,
            rate=rate,
            pitch=pitch,
            max_words=max_words,
            output_directory=output_directory,
            output_stem=output_stem,
            mode=mode,
            parent=self,
        )

        self.tts_worker.progress_changed.connect(
            self.on_tts_progress
        )
        self.tts_worker.result_ready.connect(
            self.on_tts_result
        )
        self.tts_worker.error_occurred.connect(
            self.on_tts_error
        )
        self.tts_worker.finished.connect(
            self.on_tts_thread_finished
        )

        self.tts_worker.start()

    def on_tts_progress(
        self,
        value: int,
        message: str,
    ):
        self.progress_bar.setValue(value)
        self.status_label.setText(
            f"وضعیت: {message}"
        )

    def on_tts_result(
        self,
        mp3_path: str,
        srt_path: str,
        timing_path: str,
        mode: str,
    ):
        audio_path = Path(mp3_path)
        subtitle_path = Path(srt_path)
        words_path = Path(timing_path)

        if mode == "sample":
            self.status_label.setText(
                "وضعیت: نمونه صدا آماده و در حال پخش است"
            )
            self.play_audio(audio_path)
            return

        self.generated_audio_path = audio_path
        self.generated_srt_path = subtitle_path
        self.generated_timing_path = words_path

        self.status_label.setText(
            "وضعیت: فایل MP3 و زیرنویس SRT آماده شدند"
        )
        self.progress_bar.setValue(100)

        QMessageBox.information(
            self,
            "تولید با موفقیت انجام شد",
            "فایل‌های زیر ساخته شدند:\n\n"
            f"صوت:\n{audio_path}\n\n"
            f"زیرنویس:\n{subtitle_path}\n\n"
            f"زمان‌بندی کلمات:\n{words_path}"
        )

        self.play_audio(audio_path)

    def on_tts_error(self, message: str):
        self.progress_bar.setValue(0)
        self.status_label.setText(
            "وضعیت: خطا در تولید صدا"
        )

        QMessageBox.critical(
            self,
            "خطای Edge-TTS",
            "تولید صدا یا زیرنویس انجام نشد.\n\n"
            f"{message}\n\n"
            "اتصال اینترنت را بررسی کرده و دوباره تلاش کنید."
        )

    def on_tts_thread_finished(self):
        self.sample_button.setEnabled(True)
        self.generate_audio_button.setEnabled(True)

    def play_audio(self, audio_path: Path):
        if not audio_path.exists():
            QMessageBox.warning(
                self,
                "فایل صوتی پیدا نشد",
                str(audio_path)
            )
            return

        self.media_player.stop()
        self.media_player.setSource(
            QUrl.fromLocalFile(str(audio_path.resolve()))
        )
        self.media_player.play()

    def show_upcoming_message(self):
        QMessageBox.information(
            self,
            "رابط کاربری آماده است",
            "این دکمه در مرحله بعد به موتور تبدیل متن به صوت، "
            "تولید زیرنویس و FFmpeg متصل خواهد شد."
        )

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls()

        if not urls:
            return

        suffix = Path(urls[0].toLocalFile()).suffix.lower()

        if (
            suffix in SUPPORTED_TEXT_EXTENSIONS
            or suffix in SUPPORTED_IMAGE_EXTENSIONS
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()

        if not urls:
            return

        file_path = Path(urls[0].toLocalFile())
        suffix = file_path.suffix.lower()

        if suffix in SUPPORTED_TEXT_EXTENSIONS:
            self.load_text_file(file_path)
            self.navigation.setCurrentRow(0)

        elif suffix in SUPPORTED_IMAGE_EXTENSIONS:
            pixmap = QPixmap(str(file_path))

            if not pixmap.isNull():
                self.current_image_file = file_path
                self.image_path_label.setText(str(file_path))

                scaled = pixmap.scaled(
                    self.image_preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

                self.image_preview.setPixmap(scaled)
                self.navigation.setCurrentRow(3)

        event.acceptProposedAction()

    def apply_style(self):
        self.setStyleSheet("""
            * {
                font-family: "Segoe UI", "Tahoma";
                font-size: 14px;
            }

            QMainWindow, QWidget {
                background-color: #0b1120;
                color: #e5e7eb;
            }

            QFrame#header {
                background-color: #111a2e;
                border: 1px solid #26334d;
                border-radius: 16px;
            }

            QLabel#appTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f8fafc;
            }

            QLabel#appSubtitle,
            QLabel#pageDescription {
                color: #94a3b8;
            }

            QLabel#versionBadge {
                color: #c4b5fd;
                background-color: #312e81;
                border: 1px solid #4f46e5;
                border-radius: 17px;
                font-weight: 600;
            }

            QLabel#pageTitle {
                font-size: 22px;
                font-weight: 700;
                color: #f8fafc;
            }

            QListWidget#navigation {
                background-color: #111827;
                border: 1px solid #26334d;
                border-radius: 16px;
                padding: 10px;
                outline: none;
            }

            QListWidget#navigation::item {
                color: #cbd5e1;
                min-height: 54px;
                padding: 0 15px;
                margin: 3px 0;
                border-radius: 11px;
            }

            QListWidget#navigation::item:hover {
                background-color: #1e293b;
                color: white;
            }

            QListWidget#navigation::item:selected {
                background-color: #4f46e5;
                color: white;
                font-weight: 700;
            }

            QStackedWidget#pages {
                background-color: transparent;
            }

            QFrame#card {
                background-color: #111827;
                border: 1px solid #26334d;
                border-radius: 15px;
            }

            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 700;
                color: #f1f5f9;
            }

            QLabel#pathLabel,
            QLabel#statistics,
            QLabel#summary {
                color: #a5b4fc;
            }

            QLabel#valueBadge {
                min-width: 72px;
                padding: 7px;
                background-color: #1e293b;
                border: 1px solid #334155;
                border-radius: 8px;
            }

            QPlainTextEdit {
                background-color: #0f172a;
                color: #f8fafc;
                selection-background-color: #4f46e5;
                border: 1px solid #334155;
                border-radius: 12px;
                padding: 14px;
                font-size: 15px;
                line-height: 1.6;
            }

            QPlainTextEdit:focus,
            QComboBox:focus,
            QSpinBox:focus {
                border: 1px solid #6366f1;
            }

            QPushButton {
                background-color: #1e293b;
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 9px;
                min-height: 38px;
                padding: 0 18px;
                font-weight: 600;
            }

            QPushButton:hover {
                background-color: #334155;
                border-color: #475569;
            }

            QPushButton:pressed {
                background-color: #0f172a;
            }

            QPushButton#primaryButton {
                background-color: #4f46e5;
                color: white;
                border-color: #6366f1;
            }

            QPushButton#primaryButton:hover {
                background-color: #6366f1;
            }

            QPushButton#renderButton {
                background-color: #059669;
                color: white;
                border-color: #10b981;
                min-height: 46px;
                font-size: 15px;
            }

            QPushButton#renderButton:hover {
                background-color: #10b981;
            }

            QComboBox, QSpinBox {
                background-color: #0f172a;
                color: #f1f5f9;
                border: 1px solid #334155;
                border-radius: 9px;
                min-height: 38px;
                padding: 0 12px;
            }

            QComboBox::drop-down {
                border: none;
                width: 28px;
            }

            QComboBox QAbstractItemView {
                background-color: #111827;
                color: #f8fafc;
                selection-background-color: #4f46e5;
                border: 1px solid #334155;
            }

            QSlider::groove:horizontal {
                height: 6px;
                background-color: #334155;
                border-radius: 3px;
            }

            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                margin: -6px 0;
                background-color: #818cf8;
                border-radius: 9px;
            }

            QSlider::sub-page:horizontal {
                background-color: #4f46e5;
                border-radius: 3px;
            }

            QRadioButton {
                spacing: 9px;
                min-height: 30px;
            }

            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }

            QLabel#subtitlePreview {
                color: white;
                background-color: rgba(0, 0, 0, 175);
                border: 1px solid #475569;
                border-radius: 12px;
                font-size: 22px;
                font-weight: 700;
            }

            QLabel#imagePreview {
                color: #64748b;
                background-color: #080d18;
                border: 2px dashed #334155;
                border-radius: 13px;
            }

            QFrame#statusFrame {
                background-color: #111827;
                border: 1px solid #26334d;
                border-radius: 12px;
            }

            QLabel#statusLabel {
                color: #cbd5e1;
            }

            QProgressBar {
                background-color: #0f172a;
                color: white;
                border: 1px solid #334155;
                border-radius: 8px;
                text-align: center;
                min-height: 20px;
            }

            QProgressBar::chunk {
                background-color: #4f46e5;
                border-radius: 7px;
            }

            QMessageBox {
                background-color: #111827;
            }
        """)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("استودیو متن به ویدئو")
    app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()