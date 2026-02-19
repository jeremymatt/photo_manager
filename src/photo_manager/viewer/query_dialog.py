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
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from photo_manager.db.manager import DatabaseManager
from photo_manager.query.engine import QueryEngine
from photo_manager.query.parser import QueryParseError


class QueryDialog(QDialog):
    """Dialog for entering a tag query expression to filter images."""

    def __init__(
        self,
        db: DatabaseManager,
        initial_query: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._db = db
        self._engine = QueryEngine(db)
        self._result_query: str | None = None
        self._setup_ui()
        if initial_query:
            self._input.setText(initial_query)

    @property
    def result_query(self) -> str | None:
        """The query string entered, or None if 'All images' was selected."""
        return self._result_query

    def _setup_ui(self) -> None:
        self.setWindowTitle("Filter Images")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)

        layout = QVBoxLayout(self)

        # Instructions
        label = QLabel(
            "Enter a query expression to filter images, or click 'All Images' to load everything.\n\n"
            "Example: tag.person.alice && tag.datetime.year>=2018\n"
            "Negation: !tag.scene.indoor\n"
            "Wildcards: tag.outdoor.hike* (with children)\n\n"
            "Double-click a tag below to insert it."
        )
        label.setWordWrap(True)
        layout.addWidget(label)

        # Query input
        self._input = QLineEdit()
        self._input.setFont(QFont("Consolas", 11))
        self._input.setPlaceholderText("tag.person.alice && tag.scene.outdoor")
        self._input.returnPressed.connect(self._on_apply)
        layout.addWidget(self._input)

        # Status/error label
        self._status = QLabel("")
        self._status.setStyleSheet("color: gray;")
        layout.addWidget(self._status)

        # Tag picker tree
        self._tag_tree = QTreeWidget()
        self._tag_tree.setHeaderLabels(["Available Tags"])
        self._tag_tree.setFont(QFont("Consolas", 10))
        self._tag_tree.itemDoubleClicked.connect(self._on_tag_double_click)
        self._populate_tag_tree()
        layout.addWidget(self._tag_tree, 1)

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

    def _populate_tag_tree(self) -> None:
        """Build the tag picker tree showing only tags actually applied to images."""
        # Get tag IDs actually used in image_tags
        rows = self._db.execute_query(
            "SELECT DISTINCT tag_id FROM image_tags", ()
        )
        used_ids: set[int] = {r[0] for r in rows}
        if not used_ids:
            return

        # Collect ancestor IDs so parent nodes are shown for hierarchy
        all_tags = {t.id: t for t in self._db.get_all_tag_definitions()}
        relevant_ids: set[int] = set()
        for tag_id in used_ids:
            current = tag_id
            while current is not None and current not in relevant_ids:
                relevant_ids.add(current)
                parent_id = all_tags[current].parent_id
                current = parent_id

        # Build filtered tree
        tree_data = self._db.get_tag_tree()

        def add_nodes(
            parent_item: QTreeWidgetItem | None,
            nodes: list[dict],
            prefix: str,
        ) -> None:
            for node in nodes:
                tag = node["tag"]
                if tag.id not in relevant_ids:
                    continue
                path = f"{prefix}.{tag.name}" if prefix else tag.name
                item = QTreeWidgetItem()
                item.setText(0, path)
                item.setData(0, Qt.ItemDataRole.UserRole, path)
                if parent_item is None:
                    self._tag_tree.addTopLevelItem(item)
                else:
                    parent_item.addChild(item)
                add_nodes(item, node["children"], path)

        add_nodes(None, tree_data, "")
        self._tag_tree.expandAll()

    def _on_tag_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        """Insert the double-clicked tag path at the cursor position."""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path is None:
            return
        insert_text = f"tag.{path}"

        current = self._input.text()
        cursor_pos = self._input.cursorPosition()

        # Add && separator if appending after existing text
        if current and cursor_pos > 0 and current[cursor_pos - 1] not in (" ", "(", "!"):
            insert_text = " && " + insert_text

        new_text = current[:cursor_pos] + insert_text + current[cursor_pos:]
        self._input.setText(new_text)
        self._input.setCursorPosition(cursor_pos + len(insert_text))
        self._input.setFocus()

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
