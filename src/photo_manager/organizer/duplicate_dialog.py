"""Duplicate detection progress dialog."""

from __future__ import annotations

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.hashing.duplicates import DuplicateDetector


class _DuplicateThread(QThread):
    """Background thread for duplicate detection.

    Opens its own DB connection since SQLite connections can't cross threads.
    """

    progress = pyqtSignal(int, int)  # current_pairs, total_pairs
    finished_detection = pyqtSignal(int, int)  # group_count, total_images

    def __init__(self, db_path: str, threshold: int = 5, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._threshold = threshold
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        thread_db = DatabaseManager()
        thread_db.open_database(self._db_path)
        thread_db._conn.execute("PRAGMA busy_timeout=5000")

        try:
            detector = DuplicateDetector(thread_db, self._threshold)

            def progress_callback(current: int, total: int) -> None:
                if self._cancelled:
                    raise InterruptedError("Detection cancelled")
                self.progress.emit(current, total)

            groups = detector.find_duplicates(progress_callback)
            detector.store_duplicate_groups(groups)

            total_images = sum(len(g) for g in groups)
            self.finished_detection.emit(len(groups), total_images)
        except InterruptedError:
            self.finished_detection.emit(0, 0)
        except Exception:
            self.finished_detection.emit(0, 0)
        finally:
            thread_db.close()


class DuplicateDetectionDialog(QDialog):
    """Shows duplicate detection progress with cancel and review support."""

    review_requested = pyqtSignal()

    def __init__(
        self,
        db: DatabaseManager,
        config: ConfigManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._config = config or ConfigManager()
        self._found_groups = 0

        self.setWindowTitle("Duplicate Detection")
        self.setMinimumWidth(500)
        self.setMinimumHeight(150)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._status_label = QLabel("Checking for existing duplicate groups...")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        layout.addWidget(self._progress_bar)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self._cancel_btn)

        self._review_btn = QPushButton("Review Duplicates")
        self._review_btn.setVisible(False)
        self._review_btn.clicked.connect(self._on_review)
        layout.addWidget(self._review_btn)

        # Check for existing groups
        existing = db.get_duplicate_groups()
        if existing:
            reply = QMessageBox.question(
                self,
                "Existing Groups",
                f"{len(existing)} existing duplicate group(s) found.\n"
                "Re-detect (clears old groups) or review existing?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                # Review existing
                self._found_groups = len(existing)
                total_images = sum(len(g.members) for g in existing)
                self._status_label.setText(
                    f"Existing: {len(existing)} group(s) with "
                    f"{total_images} total images"
                )
                self._progress_bar.setVisible(False)
                self._cancel_btn.setText("Close")
                self._cancel_btn.clicked.disconnect()
                self._cancel_btn.clicked.connect(self.accept)
                self._review_btn.setVisible(True)
                return
            else:
                # Clear old groups
                for g in existing:
                    db.delete_duplicate_group(g.id)

        self._start_detection()

    def _start_detection(self) -> None:
        self._status_label.setText("Detecting duplicates...")
        threshold = self._config.get(
            "duplicate_detection.similarity_threshold", 10
        )
        self._thread = _DuplicateThread(
            str(self._db.db_path), threshold
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_detection.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, current: int, total: int) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(
            f"Comparing pairs: {current}/{total}..."
        )

    def _on_finished(self, group_count: int, total_images: int) -> None:
        self._found_groups = group_count
        self._cancel_btn.setText("Close")
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)
        self._progress_bar.setValue(self._progress_bar.maximum())

        if group_count > 0:
            self._status_label.setText(
                f"Found {group_count} group(s) with "
                f"{total_images} total duplicate images"
            )
            self._review_btn.setVisible(True)
        else:
            self._status_label.setText("No duplicates found.")

    def _on_review(self) -> None:
        self.review_requested.emit()
        self.accept()

    def _cancel(self) -> None:
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._thread.cancel()
            self._status_label.setText("Cancelling...")
            self._cancel_btn.setEnabled(False)

    def closeEvent(self, event) -> None:
        if hasattr(self, "_thread") and self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait()
        super().closeEvent(event)
