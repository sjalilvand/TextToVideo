from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from app.features.subtitles.editor_dialog import SubtitleEditorDialog


def main() -> int:
    subtitle_path = PROJECT_ROOT / "output" / "narration-generated.edited.srt"

    print(f"[Subtitle Editor] Project root: {PROJECT_ROOT}")
    print(f"[Subtitle Editor] SRT source: {subtitle_path}")

    if not subtitle_path.exists():
        raise FileNotFoundError(f"فایل زیرنویس پیدا نشد: {subtitle_path}")

    application = QApplication.instance() or QApplication(sys.argv)
    application.setApplicationName("TextToVideo Subtitle Editor")
    application.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    application.setQuitOnLastWindowClosed(False)

    dialog = SubtitleEditorDialog(subtitle_path)

    print(f"[Diagnostic] Dialog type: {type(dialog)}")
    print(f"[Diagnostic] Is QDialog: {isinstance(dialog, QDialog)}")
    print(f"[Diagnostic] Title: {dialog.windowTitle()!r}")
    print(f"[Diagnostic] Visible before exec: {dialog.isVisible()}")
    print(f"[Diagnostic] Enabled: {dialog.isEnabled()}")
    print(f"[Diagnostic] Window flags: {dialog.windowFlags()}")

    dialog.accepted.connect(
        lambda: print("[Diagnostic] Signal emitted: accepted")
    )
    dialog.rejected.connect(
        lambda: print("[Diagnostic] Signal emitted: rejected")
    )
    dialog.finished.connect(
        lambda result: print(
            f"[Diagnostic] Signal emitted: finished({result})"
        )
    )

    def inspect_after_show() -> None:
        print(
            "[Diagnostic] After event loop: "
            f"visible={dialog.isVisible()}, "
            f"result={dialog.result()}, "
            f"title={dialog.windowTitle()!r}"
        )

    QTimer.singleShot(500, inspect_after_show)

    print("[Subtitle Editor] Opening dialog...")
    result = dialog.exec()

    print(f"[Subtitle Editor] Dialog closed. Result: {result}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())

    except Exception as error:
        print(
            f"[Subtitle Editor] Fatal error: {error!r}",
            file=sys.stderr,
        )

        app = QApplication.instance() or QApplication(sys.argv)

        QMessageBox.critical(
            None,
            "خطا در اجرای ویرایشگر زیرنویس",
            str(error),
        )

        raise

