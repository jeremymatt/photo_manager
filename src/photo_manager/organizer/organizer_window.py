"""Main organizer window composing all views and controls."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QAction, QKeyEvent
from PyQt6.QtWidgets import (
    QApplication,
    QInputDialog,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QStatusBar,
)

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.organizer.db_dialog import DatabaseDialog
from photo_manager.organizer.image_source import ImageSource
from photo_manager.organizer.import_dialog import ImportDialog
from photo_manager.organizer.organizer_key_handler import (
    OrganizerAction,
    OrganizerKeyHandler,
)
from photo_manager.organizer.progress_dialog import ProgressDialog
from photo_manager.organizer.tag_dialog import TagDialog
from photo_manager.organizer.view_manager import ViewManager, ViewMode
from photo_manager.viewer.help_overlay import HelpOverlay

ORGANIZER_HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Views", [
        ("Tab", "Toggle grid / single-image view"),
        ("F11", "Toggle fullscreen"),
    ]),
    ("Navigation (Single View)", [
        ("Right / Left", "Next / previous image"),
        ("Shift+Right / Left", "Next / previous folder"),
        ("F10", "Go to image number"),
    ]),
    ("Image Adjustments (Single View)", [
        ("Up / Down", "Rotate CCW / CW"),
        ("Ctrl+Up / Down", "Brightness up / down"),
        ("Alt+Up / Down", "Contrast up / down"),
        ("Mouse Wheel", "Zoom in / out"),
        ("Click + Drag", "Pan image"),
        ("Ctrl+R", "Reset image"),
        ("Ctrl+I", "Toggle info display"),
        ("F9", "Cycle info detail level"),
    ]),
    ("GIF (Single View)", [
        ("+ / =", "Increase GIF speed"),
        ("- / _", "Decrease GIF speed"),
    ]),
    ("Tags", [
        ("F2", "Edit tags dialog"),
        ("F", "Toggle favorite"),
        ("D", "Toggle to-delete"),
        ("R", "Toggle reviewed"),
    ]),
    ("Database", [
        ("F4", "Import directory"),
        ("F1", "Check / add directory"),
    ]),
    ("Other", [
        ("Alt+M", "Show / hide this help"),
        ("Esc", "Quit"),
    ]),
]


class OrganizerWindow(QMainWindow):
    """Photo organizer main window."""

    def __init__(
        self,
        db: DatabaseManager,
        config: ConfigManager | None = None,
        import_dir: str | None = None,
        start_view: str | None = None,
        start_fullscreen: bool | None = None,
    ):
        super().__init__()
        self._db = db
        self._config = config or ConfigManager()

        self.setWindowTitle("Photo Manager - Organizer")
        self.setStyleSheet("background-color: #1a1a1a; color: #cccccc;")
        w = self._config.get("ui.default_window_width", 1200)
        h = self._config.get("ui.default_window_height", 800)
        self.resize(w, h)

        # Image source
        self._source = ImageSource(db)

        # View manager
        if start_view:
            self._config.set("organizer.default_view", start_view)
        self._view_manager = ViewManager(self._source, self._config)
        self.setCentralWidget(self._view_manager)
        self._view_manager.view_changed.connect(self._on_view_changed)
        self._view_manager.grid_view.context_menu_requested.connect(
            self._edit_tags
        )

        # Key handler
        self._key_handler = OrganizerKeyHandler(self)
        self._key_handler.action_triggered.connect(self._on_action)
        self._key_handler.load_custom_bindings(self._config)

        # Install app-level event filter so Tab is caught before child
        # widgets consume it for focus traversal
        QApplication.instance().installEventFilter(self)

        # Help overlay
        self._help = HelpOverlay(
            self._view_manager, sections=ORGANIZER_HELP_SECTIONS
        )

        # Menu bar
        self._setup_menu_bar()

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._update_status()

        # Fullscreen
        fs = start_fullscreen
        if fs is None:
            fs = self._config.get("ui.start_fullscreen", False)
        if fs:
            self.menuBar().hide()
            self.statusBar().hide()
            self.showFullScreen()

        # Auto-import if requested
        if import_dir:
            self._do_import(import_dir)

    def _setup_menu_bar(self) -> None:
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        new_db_action = QAction("&New Database...", self)
        new_db_action.triggered.connect(self._new_database)
        file_menu.addAction(new_db_action)

        open_db_action = QAction("&Open Database...", self)
        open_db_action.triggered.connect(self._open_database)
        file_menu.addAction(open_db_action)

        file_menu.addSeparator()

        import_action = QAction("&Import Directory... (F4)", self)
        import_action.triggered.connect(lambda: self._do_import())
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        toggle_view = QAction("Toggle &Grid/Single (Tab)", self)
        toggle_view.triggered.connect(self._view_manager.toggle_view)
        view_menu.addAction(toggle_view)

        toggle_fs = QAction("Toggle &Fullscreen (F11)", self)
        toggle_fs.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(toggle_fs)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        shortcuts_action = QAction("&Keyboard Shortcuts (Alt+M)", self)
        shortcuts_action.triggered.connect(self._help.toggle)
        help_menu.addAction(shortcuts_action)

    def _on_view_changed(self, mode: str) -> None:
        self._key_handler.grid_mode = (mode == ViewMode.GRID)
        self._update_status()

    def _on_action(self, action: OrganizerAction) -> None:
        # Dismiss help on any action except toggle help
        if action != OrganizerAction.TOGGLE_HELP and self._help.isVisible():
            self._help.dismiss()
            return

        single = self._view_manager.single_view

        if action == OrganizerAction.TOGGLE_VIEW:
            self._view_manager.toggle_view()
        elif action == OrganizerAction.NEXT_IMAGE:
            single.navigate_next()
        elif action == OrganizerAction.PREV_IMAGE:
            single.navigate_prev()
        elif action == OrganizerAction.NEXT_FOLDER:
            single.navigate_next_folder()
        elif action == OrganizerAction.PREV_FOLDER:
            single.navigate_prev_folder()
        elif action == OrganizerAction.ROTATE_CCW:
            single.canvas.rotate_ccw()
        elif action == OrganizerAction.ROTATE_CW:
            single.canvas.rotate_cw()
        elif action == OrganizerAction.BRIGHTNESS_UP:
            single.canvas.adjust_brightness(0.1)
        elif action == OrganizerAction.BRIGHTNESS_DOWN:
            single.canvas.adjust_brightness(-0.1)
        elif action == OrganizerAction.CONTRAST_UP:
            single.canvas.adjust_contrast(0.1)
        elif action == OrganizerAction.CONTRAST_DOWN:
            single.canvas.adjust_contrast(-0.1)
        elif action == OrganizerAction.CYCLE_ZOOM_MODE:
            single.canvas.cycle_zoom_mode()
        elif action == OrganizerAction.GIF_SPEED_UP:
            pass  # Handled by SingleImageView internally
        elif action == OrganizerAction.GIF_SPEED_DOWN:
            pass
        elif action == OrganizerAction.RESET_IMAGE:
            single.canvas.reset()
        elif action == OrganizerAction.TOGGLE_INFO:
            single.info_overlay.toggle_visible()
        elif action == OrganizerAction.CYCLE_INFO_LEVEL:
            single.info_overlay.cycle_level()
        elif action == OrganizerAction.GOTO_IMAGE:
            self._goto_dialog()
        elif action == OrganizerAction.TOGGLE_FULLSCREEN:
            self._toggle_fullscreen()
        elif action == OrganizerAction.TOGGLE_RANDOM_ORDER:
            pass  # TODO: implement random order
        elif action == OrganizerAction.TOGGLE_HELP:
            self._help.toggle()
        elif action == OrganizerAction.TOGGLE_SLIDESHOW_PAUSE:
            pass  # Slideshow not yet in organizer
        elif action == OrganizerAction.IMPORT_DIRECTORY:
            self._do_import()
        elif action == OrganizerAction.CHECK_ADD_DIRECTORY:
            self._do_import()
        elif action == OrganizerAction.EDIT_TAGS:
            self._edit_tags()
        elif action == OrganizerAction.TOGGLE_FAVORITE:
            self._toggle_fixed_field("favorite")
        elif action == OrganizerAction.TOGGLE_DELETE:
            self._toggle_fixed_field("to_delete")
        elif action == OrganizerAction.TOGGLE_REVIEWED:
            self._toggle_fixed_field("reviewed")
        elif action == OrganizerAction.TOGGLE_CUSTOM_TAG:
            self._toggle_custom_tag()
        elif action == OrganizerAction.QUIT:
            self.close()

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.menuBar().show()
            self.statusBar().show()
            self.showNormal()
        else:
            self.menuBar().hide()
            self.statusBar().hide()
            self.showFullScreen()

    def _goto_dialog(self) -> None:
        total = self._source.total
        if total == 0:
            return
        num, ok = QInputDialog.getInt(
            self, "Go to Image",
            f"Image number (1-{total}):",
            value=self._view_manager.single_view.current_index + 1,
            min=1, max=total,
        )
        if ok:
            if self._view_manager.mode == ViewMode.SINGLE:
                self._view_manager.single_view.goto(num - 1)
            else:
                self._view_manager.grid_view.select_index(num - 1)

    def _new_database(self) -> None:
        dialog = DatabaseDialog(self)
        dialog._radio_create.setChecked(True)
        if dialog.exec() == DatabaseDialog.DialogCode.Accepted:
            self._switch_database(dialog.db_path, is_new=True)

    def _open_database(self) -> None:
        dialog = DatabaseDialog(self)
        dialog._radio_open.setChecked(True)
        if dialog.exec() == DatabaseDialog.DialogCode.Accepted:
            self._switch_database(dialog.db_path, is_new=False)

    def _switch_database(self, db_path: str, is_new: bool) -> None:
        self._view_manager.shutdown()
        self._db.close()

        if is_new:
            self._db.create_database(db_path)
        else:
            self._db.open_database(db_path)

        self._config.set("organizer.last_db_path", db_path)
        self._source = ImageSource(self._db)
        self._view_manager = ViewManager(self._source, self._config)
        self.setCentralWidget(self._view_manager)
        self._view_manager.view_changed.connect(self._on_view_changed)
        self._view_manager.grid_view.context_menu_requested.connect(
            self._edit_tags
        )
        self._update_status()

    def _do_import(self, directory: str | None = None) -> None:
        dialog = ImportDialog(self._db, initial_dir=directory, parent=self)
        if dialog.exec() == ImportDialog.DialogCode.Accepted:
            progress = ProgressDialog(
                db=self._db,
                directory=dialog.directory,
                templates=dialog.templates or None,
                recursive=dialog.recursive,
                config=self._config,
                parent=self,
            )
            progress.exec()
            # Refresh after dialog closes to pick up changes from scan thread
            self._source.refresh()
            self._update_status()

    def _get_selected_records(self) -> list[ImageRecord]:
        """Get ImageRecords for the currently selected image(s)."""
        from photo_manager.db.models import ImageRecord

        if self._view_manager.mode == ViewMode.GRID:
            indices = self._view_manager.grid_view.get_selected_indices()
        else:
            indices = [self._view_manager.single_view.current_index]

        records = []
        for idx in indices:
            record = self._source.get_record(idx)
            if record is not None:
                records.append(record)
        return records

    def _edit_tags(self) -> None:
        """Open tag dialog for selected images."""
        records = self._get_selected_records()
        if not records:
            return
        dialog = TagDialog(self._db, records, parent=self)
        if dialog.exec() == TagDialog.DialogCode.Accepted:
            self._source.refresh()
            self._update_status()

    def _toggle_fixed_field(self, field: str) -> None:
        """Toggle a boolean field (favorite/to_delete/reviewed) on selected images."""
        records = self._get_selected_records()
        if not records:
            return
        for record in records:
            if record.id is None:
                continue
            current = getattr(record, field)
            setattr(record, field, not current)
            self._db.update_image(record)
        self._update_status()

    def _toggle_custom_tag(self) -> None:
        """Toggle a custom tag keybinding on selected images."""
        tag_path = self._key_handler.get_last_custom_tag_path()
        if not tag_path:
            return
        records = self._get_selected_records()
        if not records:
            return

        tag_def = self._db.ensure_tag_path(tag_path)
        for record in records:
            if record.id is None:
                continue
            existing = self._db.get_image_tags(record.id)
            has_tag = any(t.tag_id == tag_def.id for t in existing)
            if has_tag:
                self._db.remove_image_tag(record.id, tag_def.id)
            else:
                self._db.set_image_tag(record.id, tag_def.id)
        self._update_status()

    def _update_status(self) -> None:
        db_name = (
            Path(self._db.db_path).name if self._db.db_path else "No DB"
        )
        mode = self._view_manager.mode.capitalize()
        total = self._source.total
        self._status_bar.showMessage(
            f"DB: {db_name}  |  {total} images  |  {mode} view"
        )

    def eventFilter(self, obj, event: QEvent) -> bool:
        """Catch Tab at the application level before focus traversal."""
        if event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Tab:
                if self._key_handler.handle_key_event(event):
                    return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self._key_handler.handle_key_event(event):
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_help"):
            self._help.setGeometry(self.centralWidget().geometry())

    def closeEvent(self, event) -> None:
        QApplication.instance().removeEventFilter(self)
        self._view_manager.shutdown()
        self._db.close()
        super().closeEvent(event)
