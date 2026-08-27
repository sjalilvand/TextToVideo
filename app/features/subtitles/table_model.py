from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
)
from PySide6.QtGui import QColor

from .model import SubtitleCue
from .srt_service import SrtFormatError, SrtService


class SubtitleTableModel(QAbstractTableModel):
    COLUMN_NUMBER = 0
    COLUMN_START = 1
    COLUMN_END = 2
    COLUMN_DURATION = 3
    COLUMN_TEXT = 4

    HEADERS = [
        "شماره",
        "شروع",
        "پایان",
        "مدت",
        "متن زیرنویس",
    ]

    def __init__(
        self,
        cues: Iterable[SubtitleCue] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._cues: list[SubtitleCue] = [
            cue.clone()
            for cue in (cues or [])
        ]

        SrtService.reindex(self._cues)

    @property
    def cues(self) -> list[SubtitleCue]:
        return self._cues

    def cue_at(self, row: int) -> SubtitleCue | None:
        if 0 <= row < len(self._cues):
            return self._cues[row]

        return None

    def rowCount(
        self,
        parent: QModelIndex = QModelIndex(),
    ) -> int:
        if parent.isValid():
            return 0

        return len(self._cues)

    def columnCount(
        self,
        parent: QModelIndex = QModelIndex(),
    ) -> int:
        if parent.isValid():
            return 0

        return len(self.HEADERS)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.DisplayRole,
    ):
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]

            return None

        return section + 1

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.DisplayRole,
    ):
        if not index.isValid():
            return None

        cue = self.cue_at(index.row())

        if cue is None:
            return None

        column = index.column()

        if role in (Qt.DisplayRole, Qt.EditRole):
            if column == self.COLUMN_NUMBER:
                return cue.index

            if column == self.COLUMN_START:
                return SrtService.ms_to_timestamp(cue.start_ms)

            if column == self.COLUMN_END:
                return SrtService.ms_to_timestamp(cue.end_ms)

            if column == self.COLUMN_DURATION:
                return SrtService.ms_to_timestamp(cue.duration_ms)

            if column == self.COLUMN_TEXT:
                return cue.text

        if role == Qt.TextAlignmentRole:
            if column == self.COLUMN_TEXT:
                return int(
                    Qt.AlignRight
                    | Qt.AlignVCenter
                )

            return int(Qt.AlignCenter)

        if role == Qt.ToolTipRole:
            errors = cue.validate()

            if errors:
                return "\n".join(errors)

            return (
                f"مدت نمایش: {cue.duration_ms:,} میلی‌ثانیه"
            )

        if role == Qt.BackgroundRole:
            if cue.validate():
                return QColor("#5c2020")

            previous = (
                self._cues[index.row() - 1]
                if index.row() > 0
                else None
            )

            if (
                previous is not None
                and cue.start_ms < previous.end_ms
            ):
                return QColor("#5a4614")

        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags

        flags = (
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
        )

        if index.column() in (
            self.COLUMN_START,
            self.COLUMN_END,
            self.COLUMN_TEXT,
        ):
            flags |= Qt.ItemIsEditable

        return flags

    def setData(
        self,
        index: QModelIndex,
        value,
        role: int = Qt.EditRole,
    ) -> bool:
        if (
            role != Qt.EditRole
            or not index.isValid()
        ):
            return False

        cue = self.cue_at(index.row())

        if cue is None:
            return False

        try:
            if index.column() == self.COLUMN_START:
                cue.start_ms = SrtService.timestamp_to_ms(
                    str(value)
                )

            elif index.column() == self.COLUMN_END:
                cue.end_ms = SrtService.timestamp_to_ms(
                    str(value)
                )

            elif index.column() == self.COLUMN_TEXT:
                cue.text = (
                    str(value)
                    .replace("\r\n", "\n")
                    .replace("\r", "\n")
                    .strip()
                )

            else:
                return False

        except (TypeError, ValueError, SrtFormatError):
            return False

        left = self.index(index.row(), self.COLUMN_NUMBER)
        right = self.index(index.row(), self.COLUMN_TEXT)

        self.dataChanged.emit(
            left,
            right,
            [
                Qt.DisplayRole,
                Qt.EditRole,
                Qt.BackgroundRole,
                Qt.ToolTipRole,
            ],
        )

        if index.row() + 1 < self.rowCount():
            next_left = self.index(
                index.row() + 1,
                self.COLUMN_NUMBER,
            )
            next_right = self.index(
                index.row() + 1,
                self.COLUMN_TEXT,
            )

            self.dataChanged.emit(
                next_left,
                next_right,
                [
                    Qt.BackgroundRole,
                    Qt.ToolTipRole,
                ],
            )

        return True

    def replace_cues(
        self,
        cues: Iterable[SubtitleCue],
    ) -> None:
        self.beginResetModel()

        self._cues = [
            cue.clone()
            for cue in cues
        ]

        SrtService.reindex(self._cues)

        self.endResetModel()

    def append_after(self, row: int) -> int:
        if not self._cues:
            insert_row = 0
            start_ms = 0
            end_ms = 2_000

        else:
            row = max(0, min(row, len(self._cues) - 1))
            current = self._cues[row]

            insert_row = row + 1
            start_ms = current.end_ms

            if insert_row < len(self._cues):
                next_start = self._cues[insert_row].start_ms

                if next_start > start_ms:
                    end_ms = next_start
                else:
                    end_ms = start_ms + 2_000
            else:
                end_ms = start_ms + 2_000

        self.beginInsertRows(
            QModelIndex(),
            insert_row,
            insert_row,
        )

        self._cues.insert(
            insert_row,
            SubtitleCue(
                index=insert_row + 1,
                start_ms=start_ms,
                end_ms=end_ms,
                text="متن زیرنویس جدید",
            ),
        )

        SrtService.reindex(self._cues)

        self.endInsertRows()
        self._refresh_all()

        return insert_row

    def remove_selected_rows(
        self,
        rows: Iterable[int],
    ) -> None:
        valid_rows = sorted(
            {
                row
                for row in rows
                if 0 <= row < len(self._cues)
            },
            reverse=True,
        )

        if not valid_rows:
            return

        self.beginResetModel()

        for row in valid_rows:
            del self._cues[row]

        SrtService.reindex(self._cues)

        self.endResetModel()

    def split_row(self, row: int) -> int | None:
        cue = self.cue_at(row)

        if cue is None:
            return None

        first_text, second_text = self._split_text(cue.text)

        if not first_text or not second_text:
            return None

        duration = cue.end_ms - cue.start_ms

        if duration < 2:
            return None

        midpoint = cue.start_ms + duration // 2

        self.beginResetModel()

        self._cues[row] = cue.clone(
            end_ms=midpoint,
            text=first_text,
        )

        self._cues.insert(
            row + 1,
            cue.clone(
                start_ms=midpoint,
                text=second_text,
            ),
        )

        SrtService.reindex(self._cues)

        self.endResetModel()

        return row + 1

    def merge_rows(
        self,
        rows: Iterable[int],
    ) -> int | None:
        selected = sorted(
            {
                row
                for row in rows
                if 0 <= row < len(self._cues)
            }
        )

        if len(selected) < 2:
            return None

        expected = list(
            range(selected[0], selected[-1] + 1)
        )

        if selected != expected:
            return None

        first_row = selected[0]
        last_row = selected[-1]

        first = self._cues[first_row]
        last = self._cues[last_row]

        merged_text = "\n".join(
            self._cues[row].text.strip()
            for row in selected
            if self._cues[row].text.strip()
        )

        self.beginResetModel()

        self._cues[first_row] = first.clone(
            end_ms=last.end_ms,
            text=merged_text,
        )

        del self._cues[first_row + 1:last_row + 1]

        SrtService.reindex(self._cues)

        self.endResetModel()

        return first_row

    def shift_all(self, offset_ms: int) -> None:
        shifted = SrtService.shift(
            self._cues,
            offset_ms,
        )

        self.replace_cues(shifted)

    def _refresh_all(self) -> None:
        if not self._cues:
            return

        self.dataChanged.emit(
            self.index(0, 0),
            self.index(
                len(self._cues) - 1,
                len(self.HEADERS) - 1,
            ),
        )

    @staticmethod
    def _split_text(text: str) -> tuple[str, str]:
        normalized = text.strip()

        if "\n" in normalized:
            lines = normalized.splitlines()
            midpoint = max(1, len(lines) // 2)

            return (
                "\n".join(lines[:midpoint]).strip(),
                "\n".join(lines[midpoint:]).strip(),
            )

        words = normalized.split()

        if len(words) < 2:
            return normalized, ""

        midpoint = max(1, len(words) // 2)

        return (
            " ".join(words[:midpoint]).strip(),
            " ".join(words[midpoint:]).strip(),
        )
