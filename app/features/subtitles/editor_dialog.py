from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QModelIndex, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .srt_service import SrtService
from .table_model import SubtitleTableModel


class SubtitleEditorDialog(QDialog):
    def __init__(
        self,
        subtitle_path: str | Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self.subtitle_path: Path | None = None
        self.output_path: Path | None = None
        self._syncing_text = False

        self.setWindowTitle("ویرایشگر زیرنویس فارسی")
        self.setMinimumSize(1050, 700)
        self.resize(1250, 800)
        self.setLayoutDirection(Qt.RightToLeft)

        self.model = SubtitleTableModel(parent=self)

        self._build_ui()
        self._connect_signals()

        if subtitle_path is not None:
            self.load_subtitle(subtitle_path)
        else:
            self._update_status()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        file_toolbar = QHBoxLayout()

        self.open_button = QPushButton("باز کردن SRT")
        self.save_button = QPushButton("ذخیره نسخه ویرایش‌شده")
        self.save_as_button = QPushButton("ذخیره با نام دیگر")
        self.validate_button = QPushButton("بررسی خط زمانی")

        file_toolbar.addWidget(self.open_button)
        file_toolbar.addWidget(self.save_button)
        file_toolbar.addWidget(self.save_as_button)
        file_toolbar.addWidget(self.validate_button)
        file_toolbar.addStretch(1)

        root_layout.addLayout(file_toolbar)

        edit_toolbar = QHBoxLayout()

        self.add_button = QPushButton("افزودن ردیف")
        self.delete_button = QPushButton("حذف ردیف")
        self.split_button = QPushButton("تقسیم زیرنویس")
        self.merge_button = QPushButton("ادغام انتخاب‌ها")

        self.shift_spin = QSpinBox()
        self.shift_spin.setRange(-3_600_000, 3_600_000)
        self.shift_spin.setSingleStep(100)
        self.shift_spin.setSuffix(" ms")
        self.shift_spin.setValue(0)
        self.shift_spin.setToolTip(
            "مقدار مثبت زیرنویس را دیرتر و "
            "مقدار منفی آن را زودتر نمایش می‌دهد."
        )

        self.shift_button = QPushButton("اعمال جابه‌جایی")

        edit_toolbar.addWidget(self.add_button)
        edit_toolbar.addWidget(self.delete_button)
        edit_toolbar.addWidget(self.split_button)
        edit_toolbar.addWidget(self.merge_button)
        edit_toolbar.addSpacing(25)
        edit_toolbar.addWidget(QLabel("جابجایی همه زمان‌ها:"))
        edit_toolbar.addWidget(self.shift_spin)
        edit_toolbar.addWidget(self.shift_button)
        edit_toolbar.addStretch(1)

        root_layout.addLayout(edit_toolbar)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.ExtendedSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.table.setWordWrap(True)
        self.table.verticalHeader().setDefaultSectionSize(48)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)

        self.table.setColumnWidth(
            SubtitleTableModel.COLUMN_NUMBER,
            70,
        )
        self.table.setColumnWidth(
            SubtitleTableModel.COLUMN_START,
            135,
        )
        self.table.setColumnWidth(
            SubtitleTableModel.COLUMN_END,
            135,
        )
        self.table.setColumnWidth(
            SubtitleTableModel.COLUMN_DURATION,
            135,
        )

        editor_widget = QWidget()
        editor_layout = QVBoxLayout(editor_widget)
        editor_layout.setContentsMargins(0, 0, 0, 0)

        editor_title = QLabel(
            "ویرایش متن زیرنویس انتخاب‌شده"
        )

        self.text_editor = QTextEdit()
        self.text_editor.setPlaceholderText(
            "یک ردیف از جدول را انتخاب کنید."
        )
        self.text_editor.setAcceptRichText(False)
        self.text_editor.setLayoutDirection(Qt.RightToLeft)
        self.text_editor.setMinimumHeight(150)

        editor_layout.addWidget(editor_title)
        editor_layout.addWidget(self.text_editor)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(editor_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        root_layout.addWidget(splitter, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "padding: 8px;"
            "border: 1px solid #555;"
            "border-radius: 5px;"
        )

        root_layout.addWidget(self.status_label)

        self.setStyleSheet(
            """
            QDialog {
                background-color: #101820;
                color: #e9f1f7;
            }

            QWidget {
                color: #e9f1f7;
                font-size: 13px;
            }

            QLabel {
                color: #dcecff;
                background-color: transparent;
            }

            QPushButton {
                background-color: #24557a;
                color: #ffffff;
                border: 1px solid #4e91bd;
                border-radius: 6px;
                padding: 8px 14px;
                min-height: 20px;
            }

            QPushButton:hover {
                background-color: #3276a5;
                border-color: #74c7ec;
            }

            QPushButton:pressed {
                background-color: #173e5a;
            }

            QPushButton:disabled {
                background-color: #34434e;
                color: #83929c;
                border-color: #4b5b65;
            }

            QTableView {
                background-color: #172733;
                alternate-background-color: #223b4b;
                color: #eaf6ff;
                border: 1px solid #52738a;
                border-radius: 5px;
                gridline-color: #49677a;
                selection-background-color: #1976a8;
                selection-color: #ffffff;
            }

            QTableView::item {
                color: #eaf6ff;
                padding: 7px;
                border-bottom: 1px solid #3f5d70;
            }

            QTableView::item:hover {
                background-color: #31566c;
                color: #ffffff;
            }

            QTableView::item:selected {
                background-color: #1677a8;
                color: #ffffff;
                border: 1px solid #70d6ff;
            }

            QHeaderView::section {
                background-color: #284f68;
                color: #ffffff;
                padding: 8px;
                border: 0px;
                border-right: 1px solid #6c8da2;
                border-bottom: 1px solid #76a8c5;
                font-weight: bold;
            }

            QHeaderView::section:hover {
                background-color: #376f90;
            }

            QTableCornerButton::section {
                background-color: #284f68;
                border: 1px solid #6c8da2;
            }

            QTextEdit {
                background-color: #162b38;
                color: #f0f8ff;
                border: 2px solid #3d7899;
                border-radius: 6px;
                padding: 9px;
                selection-background-color: #168aad;
                selection-color: #ffffff;
            }

            QTextEdit:focus {
                border-color: #65d1ef;
                background-color: #193240;
            }

            QSpinBox {
                background-color: #1c3442;
                color: #ffffff;
                border: 1px solid #5790ae;
                border-radius: 5px;
                padding: 6px;
                selection-background-color: #168aad;
            }

            QSpinBox:focus {
                border: 2px solid #65d1ef;
            }

            QSplitter::handle {
                background-color: #3e6479;
                margin: 2px;
            }

            QSplitter::handle:hover {
                background-color: #68c4e5;
            }

            QScrollBar:vertical {
                background-color: #152630;
                width: 15px;
                margin: 0px;
            }

            QScrollBar::handle:vertical {
                background-color: #47768e;
                min-height: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:vertical:hover {
                background-color: #62b6d6;
            }

            QScrollBar:add-line:vertical,
            QScrollBar:sub-line:vertical {
                height: 0px;
            }

            QScrollBar:horizontal {
                background-color: #152630;
                height: 15px;
                margin: 0px;
            }

            QScrollBar::handle:horizontal {
                background-color: #47768e;
                min-width: 30px;
                border-radius: 6px;
                margin: 2px;
            }

            QScrollBar::handle:horizontal:hover {
                background-color: #62b6d6;
            }

            QScrollBar:add-line:horizontal,
            QScrollBar:sub-line:horizontal {
                width: 0px;
            }

            QToolTip {
                background-color: #264653;
                color: #ffffff;
                border: 1px solid #74c7ec;
                padding: 5px;
            }
            """
        )

    def _connect_signals(self) -> None:
        self.open_button.clicked.connect(
            self._choose_and_open
        )
        self.save_button.clicked.connect(
            self.save_edited_copy
        )
        self.save_as_button.clicked.connect(
            self.save_as
        )
        self.validate_button.clicked.connect(
            self.show_validation
        )

        self.add_button.clicked.connect(
            self.add_cue
        )
        self.delete_button.clicked.connect(
            self.delete_selected
        )
        self.split_button.clicked.connect(
            self.split_selected
        )
        self.merge_button.clicked.connect(
            self.merge_selected
        )
        self.shift_button.clicked.connect(
            self.shift_all
        )

        self.table.selectionModel().currentChanged.connect(
            self._current_row_changed
        )

        self.text_editor.textChanged.connect(
            self._text_editor_changed
        )

        self.model.dataChanged.connect(
            self._model_changed
        )
        self.model.rowsInserted.connect(
            self._structure_changed
        )
        self.model.rowsRemoved.connect(
            self._structure_changed
        )
        self.model.modelReset.connect(
            self._model_reset
        )

    def load_subtitle(
        self,
        path: str | Path,
    ) -> None:
        subtitle_path = Path(path)

        try:
            cues = SrtService.load(subtitle_path)

        except Exception as error:
            QMessageBox.critical(
                self,
                "خطا در باز کردن زیرنویس",
                str(error),
            )
            return

        self.subtitle_path = subtitle_path

        if subtitle_path.stem.lower().endswith(".edited"):
            self.output_path = subtitle_path
        else:
            self.output_path = subtitle_path.with_name(
                f"{subtitle_path.stem}.edited.srt"
            )

        self.model.replace_cues(cues)

        self.setWindowTitle(
            f"ویرایشگر زیرنویس — {subtitle_path.name}"
        )

        if self.model.rowCount() > 0:
            self._select_row(0)

        self._update_status()

    def _choose_and_open(self) -> None:
        start_directory = (
            str(self.subtitle_path.parent)
            if self.subtitle_path is not None
            else str(Path.cwd())
        )

        filename, _ = QFileDialog.getOpenFileName(
            self,
            "انتخاب فایل زیرنویس",
            start_directory,
            "Subtitle files (*.srt);;All files (*.*)",
        )

        if filename:
            self.load_subtitle(filename)

    def selected_rows(self) -> list[int]:
        selection_model = self.table.selectionModel()

        if selection_model is None:
            return []

        return sorted(
            {
                index.row()
                for index in selection_model.selectedRows()
            }
        )

    def current_row(self) -> int:
        index = self.table.currentIndex()

        if not index.isValid():
            return -1

        return index.row()

    def add_cue(self) -> None:
        row = self.current_row()

        if row < 0:
            row = self.model.rowCount() - 1

        inserted_row = self.model.append_after(row)
        self._select_row(inserted_row)

    def delete_selected(self) -> None:
        rows = self.selected_rows()

        if not rows:
            QMessageBox.information(
                self,
                "حذف زیرنویس",
                "ابتدا یک یا چند ردیف را انتخاب کنید.",
            )
            return

        answer = QMessageBox.question(
            self,
            "تأیید حذف",
            f"{len(rows)} زیرنویس حذف شود؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            return

        target_row = min(rows)
        self.model.remove_selected_rows(rows)

        if self.model.rowCount() > 0:
            target_row = min(
                target_row,
                self.model.rowCount() - 1,
            )
            self._select_row(target_row)
        else:
            self._clear_text_editor()

        self._update_status()

    def split_selected(self) -> None:
        row = self.current_row()

        if row < 0:
            QMessageBox.information(
                self,
                "تقسیم زیرنویس",
                "ابتدا یک زیرنویس را انتخاب کنید.",
            )
            return

        new_row = self.model.split_row(row)

        if new_row is None:
            QMessageBox.warning(
                self,
                "تقسیم انجام نشد",
                "برای تقسیم، متن باید حداقل دو کلمه "
                "و مدت زیرنویس باید معتبر باشد.",
            )
            return

        self._select_row(new_row)
        self._update_status()

    def merge_selected(self) -> None:
        rows = self.selected_rows()

        if len(rows) < 2:
            QMessageBox.information(
                self,
                "ادغام زیرنویس‌ها",
                "حداقل دو ردیف متوالی را انتخاب کنید.",
            )
            return

        merged_row = self.model.merge_rows(rows)

        if merged_row is None:
            QMessageBox.warning(
                self,
                "ادغام انجام نشد",
                "فقط ردیف‌های متوالی قابل ادغام هستند.",
            )
            return

        self._select_row(merged_row)
        self._update_status()

    def shift_all(self) -> None:
        offset_ms = self.shift_spin.value()

        if offset_ms == 0:
            QMessageBox.information(
                self,
                "جابجایی زمان",
                "مقدار جابجایی صفر است.",
            )
            return

        self.model.shift_all(offset_ms)
        self.shift_spin.setValue(0)

        if self.model.rowCount() > 0:
            self._select_row(0)

        self._update_status()

    def show_validation(self) -> None:
        warnings = SrtService.validate_timeline(
            self.model.cues
        )

        if not warnings:
            QMessageBox.information(
                self,
                "نتیجه بررسی",
                "خط زمانی زیرنویس سالم است و "
                "هیچ خطایی پیدا نشد.",
            )
            return

        preview = "\n".join(
            f"• {warning}"
            for warning in warnings[:20]
        )

        if len(warnings) > 20:
            preview += (
                f"\n\nو {len(warnings) - 20} هشدار دیگر..."
            )

        QMessageBox.warning(
            self,
            "هشدارهای خط زمانی",
            preview,
        )

    def save_edited_copy(self) -> None:
        if self.output_path is None:
            self.save_as()
            return

        self._save_to(self.output_path)

    def save_as(self) -> None:
        suggested_path = (
            self.output_path
            or (
                self.subtitle_path.with_name(
                    f"{self.subtitle_path.stem}.edited.srt"
                )
                if self.subtitle_path is not None
                else Path.cwd() / "subtitles.edited.srt"
            )
        )

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "ذخیره زیرنویس ویرایش‌شده",
            str(suggested_path),
            "Subtitle files (*.srt)",
        )

        if not filename:
            return

        output_path = Path(filename)

        if output_path.suffix.lower() != ".srt":
            output_path = output_path.with_suffix(".srt")

        self.output_path = output_path
        self._save_to(output_path)

    def _save_to(self, output_path: Path) -> None:
        warnings = SrtService.validate_timeline(
            self.model.cues
        )

        blocking_errors = []

        for position, cue in enumerate(
            self.model.cues,
            start=1,
        ):
            for error in cue.validate():
                blocking_errors.append(
                    f"زیرنویس {position}: {error}"
                )

        if blocking_errors:
            QMessageBox.critical(
                self,
                "ذخیره انجام نشد",
                "\n".join(blocking_errors[:20]),
            )
            return

        if warnings:
            answer = QMessageBox.question(
                self,
                "وجود هشدار زمانی",
                f"{len(warnings)} هشدار زمانی وجود دارد.\n"
                "آیا فایل با همین وضعیت ذخیره شود؟",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if answer != QMessageBox.Yes:
                return

        try:
            saved_path = SrtService.save(
                output_path,
                self.model.cues,
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "خطا در ذخیره زیرنویس",
                str(error),
            )
            return

        QMessageBox.information(
            self,
            "ذخیره موفق",
            f"فایل زیرنویس ذخیره شد:\n{saved_path}",
        )

        self._update_status(
            extra_message=f"ذخیره شد: {saved_path.name}"
        )

    def _current_row_changed(
        self,
        current: QModelIndex,
        previous: QModelIndex,
    ) -> None:
        del previous

        if not current.isValid():
            self._clear_text_editor()
            return

        cue = self.model.cue_at(current.row())

        if cue is None:
            self._clear_text_editor()
            return

        self._syncing_text = True
        self.text_editor.setPlainText(cue.text)
        self._syncing_text = False

    def _text_editor_changed(self) -> None:
        if self._syncing_text:
            return

        row = self.current_row()

        if row < 0:
            return

        index = self.model.index(
            row,
            SubtitleTableModel.COLUMN_TEXT,
        )

        self.model.setData(
            index,
            self.text_editor.toPlainText(),
        )

    def _model_changed(self, *args) -> None:
        del args
        self._update_status()

    def _structure_changed(self, *args) -> None:
        del args
        self._update_status()

    def _model_reset(self) -> None:
        self._clear_text_editor()
        self._update_status()

    def _clear_text_editor(self) -> None:
        self._syncing_text = True
        self.text_editor.clear()
        self._syncing_text = False

    def _select_row(self, row: int) -> None:
        if not (0 <= row < self.model.rowCount()):
            return

        index = self.model.index(
            row,
            SubtitleTableModel.COLUMN_TEXT,
        )

        self.table.setCurrentIndex(index)
        self.table.selectRow(row)
        self.table.scrollTo(index)

    def _update_status(
        self,
        *,
        extra_message: str = "",
    ) -> None:
        cues = self.model.cues
        warnings = SrtService.validate_timeline(cues)

        if cues:
            timeline_end = max(
                cue.end_ms
                for cue in cues
            )
        else:
            timeline_end = 0

        source_text = (
            str(self.subtitle_path)
            if self.subtitle_path is not None
            else "فایلی باز نشده است"
        )

        status = (
            f"فایل: {source_text} | "
            f"تعداد: {len(cues)} | "
            f"پایان: "
            f"{SrtService.ms_to_timestamp(timeline_end)} | "
            f"هشدارها: {len(warnings)}"
        )

        if extra_message:
            status += f" | {extra_message}"

        self.status_label.setText(status)
