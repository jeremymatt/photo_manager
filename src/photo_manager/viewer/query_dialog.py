"""Tag query input dialog for DB mode."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from photo_manager.db.manager import DatabaseManager
from photo_manager.query.engine import QueryEngine
from photo_manager.query.parser import QueryParseError


class QueryDialog(QDialog):
    """Dialog for entering a tag query expression to filter images."""

    def __init__(
        self, db: DatabaseManager, parent=None
    ):
        super().__init__(parent)
        self._db = db
        self._engine = QueryEngine(db)
        self._result_query: str | None = None
        self._setup_ui()

    @property
    def result_query(self) -> str | None:
        """The query string entered, or None if 'All images' was selected."""
        return self._result_query

    def _setup_ui(self) -> None:
        self.setWindowTitle("Filter Images")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel(
            "Enter a query expression to filter images, or click 'All Images' to load everything.\n\n"
            'Example: tag.person=="Alice" && tag.datetime.year>=2018'
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        # Query input
        self._input = QLineEdit()
        self._input.setFont(QFont("Consolas", 11))
        self._input.setPlaceholderText('tag.person=="Alice" && tag.event=="birthday"')
        self._input.returnPressed.connect(self._on_apply)
        layout.addWidget(self._input)

        # Status/error label
        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

        # Buttons
        btn_layout = QHBoxLayout()
        self._all_btn = QPushButton("All Images")
        self._all_btn.clicked.connect(self._on_all)
        btn_layout.addWidget(self._all_btn)

        self._preview_btn = QPushButton("Preview Count")
        self._preview_btn.clicked.connect(self._on_preview)
        btn_layout.addWidget(self._preview_btn)

        self._apply_btn = QPushButton("Apply Filter")
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.setDefault(True)
        btn_layout.addWidget(self._apply_btn)

        layout.addLayout(btn_layout)

    def _on_all(self) -> None:
        self._result_query = None
        self.accept()

    def _on_preview(self) -> None:
        query = self._input.text().strip()
        if not query:
            total = self._db.get_image_count()
            self._status.setText(f"All images: {total}")
            self._status.setStyleSheet("color: white;")
            return
        try:
            results = self._engine.query(query)
            self._status.setText(f"Matches: {len(results)} images")
            self._status.setStyleSheet("color: #88ff88;")
        except QueryParseError as e:
            self._status.setText(f"Syntax error: {e}")
            self._status.setStyleSheet("color: #ff8888;")
        except Exception as e:
            self._status.setText(f"Error: {e}")
            self._status.setStyleSheet("color: #ff8888;")

    def _on_apply(self) -> None:
        query = self._input.text().strip()
        if not query:
            self._result_query = None
            self.accept()
            return
        try:
            results = self._engine.query(query)
            self._result_query = query
            self.accept()
        except QueryParseError as e:
            self._status.setText(f"Syntax error: {e}")
            self._status.setStyleSheet("color: #ff8888;")
        except Exception as e:
            self._status.setText(f"Error: {e}")
            self._status.setStyleSheet("color: #ff8888;")
