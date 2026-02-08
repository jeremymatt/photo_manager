"""Progress dialog for scan/import operations."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.db.models import ScanResult
from photo_manager.scanner.scanner import DirectoryScanner
from photo_manager.scanner.tag_template import TagTemplate


class _ScanThread(QThread):
    """Background thread for directory scanning.

    Opens its own DB connection since SQLite connections can't cross threads.
    """

    progress = pyqtSignal(int, int, str)  # current, total, filepath
    finished_scan = pyqtSignal(object)  # ScanResult

    def __init__(
        self,
        db_path: str,
        directory: str,
        templates: list[TagTemplate] | None,
        recursive: bool,
        config: ConfigManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db_path = db_path
        self._directory = directory
        self._templates = templates
        self._recursive = recursive
        self._config = config
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        # Open a fresh DB connection in this thread
        thread_db = DatabaseManager()
        thread_db.open_database(self._db_path)

        scanner = DirectoryScanner(thread_db, self._config)

        def progress_callback(current: int, total: int, filepath: str) -> None:
            if self._cancelled:
                raise InterruptedError("Scan cancelled")
            self.progress.emit(current, total, filepath)

        try:
            result = scanner.scan_directory(
                self._directory,
                templates=self._templates,
                progress_callback=progress_callback,
                recursive=self._recursive,
            )
            self.finished_scan.emit(result)
        except InterruptedError:
            self.finished_scan.emit(
                ScanResult(total_found=0, added=0, skipped=0, errors=0)
            )
        except Exception as e:
            result = ScanResult(total_found=0, added=0, skipped=0, errors=1)
            result.error_files.append(str(e))
            self.finished_scan.emit(result)
        finally:
            thread_db.close()


class ProgressDialog(QDialog):
    """Shows scan progress with cancel support."""

    scan_complete = pyqtSignal(object)  # ScanResult

    def __init__(
        self,
        db: DatabaseManager,
        directory: str,
        templates: list[TagTemplate] | None = None,
        recursive: bool = True,
        config: ConfigManager | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Importing Images...")
        self.setMinimumWidth(500)
        self.setMinimumHeight(200)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._status_label = QLabel("Scanning directory...")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        layout.addWidget(self._progress_bar)

        self._file_label = QLabel("")
        self._file_label.setStyleSheet("color: gray; font-size: 11px;")
        self._file_label.setWordWrap(True)
        layout.addWidget(self._file_label)

        self._details = QTextEdit()
        self._details.setReadOnly(True)
        self._details.setVisible(False)
        self._details.setMaximumHeight(150)
        layout.addWidget(self._details)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.clicked.connect(self._cancel)
        layout.addWidget(self._cancel_btn)

        # Start scan thread (pass db_path so thread opens its own connection)
        self._thread = _ScanThread(
            str(db.db_path), directory, templates, recursive, config
        )
        self._thread.progress.connect(self._on_progress)
        self._thread.finished_scan.connect(self._on_finished)
        self._thread.start()

    def _on_progress(self, current: int, total: int, filepath: str) -> None:
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(current)
        self._status_label.setText(f"Processing {current}/{total}...")
        # Show just the filename
        from pathlib import Path
        self._file_label.setText(Path(filepath).name)

    def _on_finished(self, result: ScanResult) -> None:
        self._cancel_btn.setText("Close")
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)

        self._progress_bar.setValue(self._progress_bar.maximum())
        self._status_label.setText(
            f"Import complete: {result.added} added, "
            f"{result.skipped} skipped, {result.errors} errors"
        )
        self._file_label.setText("")

        if result.error_files:
            self._details.setVisible(True)
            self._details.setPlainText(
                "Errors:\n" + "\n".join(result.error_files)
            )

        self.scan_complete.emit(result)

    def _cancel(self) -> None:
        self._thread.cancel()
        self._status_label.setText("Cancelling...")
        self._cancel_btn.setEnabled(False)

    def closeEvent(self, event) -> None:
        if self._thread.isRunning():
            self._thread.cancel()
            self._thread.wait()
        super().closeEvent(event)
