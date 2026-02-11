"""Main organizer window composing all views and controls."""

from __future__ import annotations

import os
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

from photo_manager.config.config import ConfigManager, get_db_config_path
from photo_manager.db.manager import DatabaseManager
from photo_manager.organizer.db_dialog import DatabaseDialog
from photo_manager.organizer.duplicate_dialog import DuplicateDetectionDialog
from photo_manager.organizer.hash_worker import HashThread
from photo_manager.organizer.image_source import ImageSource
from photo_manager.organizer.import_dialog import ImportDialog
from photo_manager.organizer.organizer_key_handler import (
    OrganizerAction,
    OrganizerKeyHandler,
)
from photo_manager.organizer.keybinding_dialog import KeybindingDialog
from photo_manager.organizer.progress_dialog import ProgressDialog
from photo_manager.organizer.tag_dialog import TagDialog
from photo_manager.organizer.view_manager import ViewManager, ViewMode
from photo_manager.viewer.help_overlay import HelpOverlay
from photo_manager.viewer.query_dialog import QueryDialog

ORGANIZER_HELP_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    ("Views", [
        ("Tab", "Toggle grid / single-image view"),
        ("F11", "Toggle fullscreen"),
    ]),
    ("Navigation (Single View)", [
        ("Right / Left", "Next / previous image"),
        ("Alt+Right / Left", "Next / previous folder"),
        ("F10", "Go to image number"),
    ]),
    ("Image Adjustments (Single View)", [
        ("Up / Down", "Rotate CCW / CW"),
        ("Ctrl+Up / Down", "Brightness up / down"),
        ("Alt+Up / Down", "Contrast up / down"),
        ("Mouse Wheel", "Zoom in / out"),
        ("Click + Drag", "Pan image"),
        ("Ctrl+R", "Reset image"),
        ("Ctrl+Shift+S", "Save with rotation"),
        ("Ctrl+I", "Toggle info display"),
        ("F9", "Cycle info detail level"),
    ]),
    ("GIF (Single View)", [
        ("+ / =", "Increase GIF speed"),
        ("- / _", "Decrease GIF speed"),
    ]),
    ("Tags", [
        ("F2", "Edit tags dialog"),
        ("Ctrl+T", "Edit keybindings"),
        ("Alt+Shift+T", "Show tag hotkeys"),
        ("Ctrl+C", "Copy scene/event/person tags"),
        ("Ctrl+V", "Paste copied tags to image"),
        ("Ctrl+Shift+V", "Apply copied tags to folder/dup group"),
        ("F", "Set favorite (default)"),
        ("D", "Set to-delete (default)"),
        ("R", "Set reviewed (default)"),
    ]),
    ("Delete", [
        (".", "Mark for deletion & next"),
        ("Alt+.", "Unmark deletion & next"),
        ("Ctrl+Alt+D", "Mark folder & next folder"),
        ("Alt+D", "Review marked images"),
        ("Ctrl+D", "Delete marked images"),
    ]),
    ("Duplicates", [
        ("Ctrl+Shift+D", "Detect duplicates"),
        ("F3", "Enter/exit duplicate review"),
        ("Alt+Right / Left", "Next / previous dup group"),
        ("Ctrl+K", "Mark image as kept"),
        ("Ctrl+N", "Toggle not-a-duplicate"),
        ("Ctrl+D", "Delete unmarked duplicates"),
    ]),
    ("Database", [
        ("F4", "Import directory"),
        ("F5", "Query / filter images"),
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
        self._view_manager.single_view.current_index_changed.connect(
            self._on_image_changed
        )

        # Key handler
        self._key_handler = OrganizerKeyHandler(self)
        self._key_handler.action_triggered.connect(self._on_action)
        self._key_handler.load_custom_bindings(self._config)

        # Sync key handler mode — ViewManager.__init__ emits view_changed
        # before the signal connection above, so we must sync explicitly
        self._key_handler.grid_mode = (self._view_manager.mode == ViewMode.GRID)

        # Install app-level event filter so Tab is caught before child
        # widgets consume it for focus traversal
        QApplication.instance().installEventFilter(self)

        # Background hash thread reference
        self._hash_thread: HashThread | None = None

        # Copied tags clipboard (list of ImageTag)
        self._copied_tags: list = []

        # Saved query for restoring after dup review
        self._saved_query: str | None = None

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
        # Dismiss help on any action except toggle help / show tag hotkeys
        if action not in (OrganizerAction.TOGGLE_HELP, OrganizerAction.SHOW_TAG_HOTKEYS) and self._help.isVisible():
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
            if self._source.is_dup_filtered:
                self._next_dup_group()
            else:
                single.navigate_next_folder()
        elif action == OrganizerAction.PREV_FOLDER:
            if self._source.is_dup_filtered:
                self._prev_dup_group()
            else:
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
        elif action == OrganizerAction.EDIT_KEYBINDINGS:
            self._edit_keybindings()
        elif action == OrganizerAction.QUICK_BINDING:
            actions = self._key_handler.get_last_binding_actions()
            self._execute_binding(actions)
        elif action == OrganizerAction.COPY_TAGS:
            self._copy_tags()
        elif action == OrganizerAction.PASTE_TAGS:
            self._paste_tags()
        elif action == OrganizerAction.APPLY_TAGS_TO_FOLDER:
            self._apply_tags_to_folder()
        elif action == OrganizerAction.MARK_DELETE:
            if self._source.is_dup_filtered:
                self._mark_dup_group_delete()
            else:
                self._mark_delete()
        elif action == OrganizerAction.UNMARK_DELETE:
            if self._source.is_dup_filtered:
                self._unmark_dup_group_delete()
            else:
                self._unmark_delete()
        elif action == OrganizerAction.MARK_DELETE_FOLDER:
            self._mark_delete_folder()
        elif action == OrganizerAction.REVIEW_DELETIONS:
            self._review_deletions()
        elif action == OrganizerAction.EXECUTE_DELETIONS:
            if self._source.is_dup_filtered:
                self._delete_unmarked_dups()
            else:
                self._execute_deletions()
        elif action == OrganizerAction.SHOW_TAG_HOTKEYS:
            self._show_tag_hotkeys()
        elif action == OrganizerAction.QUERY_FILTER:
            self._show_query_dialog()
        elif action == OrganizerAction.DETECT_DUPLICATES:
            self._detect_duplicates()
        elif action == OrganizerAction.ENTER_DUP_REVIEW:
            self._toggle_dup_review()
        elif action == OrganizerAction.TOGGLE_NOT_DUPLICATE:
            self._toggle_not_duplicate()
        elif action == OrganizerAction.KEEP_IMAGE:
            self._keep_image()
        elif action == OrganizerAction.SAVE_WITH_ROTATION:
            self._save_with_rotation()
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

        # Reload config layered for new DB
        self._config.set("organizer.last_db_path", db_path)
        db_config_path = get_db_config_path(db_path)
        self._config.load_layered(db_config_path=db_config_path)

        self._source = ImageSource(self._db)
        self._view_manager = ViewManager(self._source, self._config)
        self.setCentralWidget(self._view_manager)
        self._view_manager.view_changed.connect(self._on_view_changed)
        self._view_manager.grid_view.context_menu_requested.connect(
            self._edit_tags
        )
        self._view_manager.single_view.current_index_changed.connect(
            self._on_image_changed
        )
        self._key_handler.load_all_bindings(self._config)
        self._key_handler.grid_mode = (self._view_manager.mode == ViewMode.GRID)
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
            # Launch background hashing
            self._start_hashing()

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
            self._update_overlay_tags()
            self._update_status()

    def _edit_keybindings(self) -> None:
        """Open keybinding editor dialog."""
        dialog = KeybindingDialog(self._config, self._key_handler, parent=self)
        dialog.exec()

    def _execute_binding(self, actions: list[str]) -> None:
        """Execute a list of binding action strings on selected images."""
        records = self._get_selected_records()
        single = self._view_manager.single_view

        for action_str in actions:
            # Fixed field set/clear
            if action_str in ("set_favorite", "clear_favorite",
                              "set_to_delete", "clear_to_delete",
                              "set_reviewed", "clear_reviewed"):
                if not records:
                    continue
                is_set = action_str.startswith("set_")
                field = action_str.split("_", 1)[1] if is_set else action_str.split("_", 1)[1]
                # Normalize: "set_to_delete" -> field="to_delete", "clear_to_delete" -> field="to_delete"
                field = action_str[len("set_"):] if is_set else action_str[len("clear_"):]
                for record in records:
                    if record.id is None:
                        continue
                    setattr(record, field, is_set)
                    self._db.update_image(record)

            # Dynamic tag add/remove
            elif action_str.startswith("tag:"):
                tag_path = action_str[4:].lower()
                if not records:
                    continue
                tag_def = self._db.ensure_tag_path(tag_path)
                for record in records:
                    if record.id is None:
                        continue
                    self._db.set_image_tag(record.id, tag_def.id)

            elif action_str.startswith("untag:"):
                tag_path = action_str[6:].lower()
                if not records:
                    continue
                tag_def = self._db.ensure_tag_path(tag_path)
                for record in records:
                    if record.id is None:
                        continue
                    self._db.remove_image_tag(record.id, tag_def.id)

            # Navigation
            elif action_str == "next_image":
                single.navigate_next()
            elif action_str == "prev_image":
                single.navigate_prev()

            # Dialogs
            elif action_str == "edit_tags":
                self._edit_tags()

        self._update_overlay_tags()
        self._update_status()

    def _on_image_changed(self, index: int) -> None:
        """Update info overlay tags when the current image changes."""
        self._update_overlay_tags(index)

    def _update_overlay_tags(self, index: int | None = None) -> None:
        """Look up tags for the current image and push to the info overlay."""
        single = self._view_manager.single_view
        if index is None:
            index = single.current_index
        record = self._source.get_record(index)
        if record is None or record.id is None:
            single.info_overlay.set_tags([])
            return
        image_tags = self._db.get_image_tags(record.id)
        tag_strings = []
        for it in image_tags:
            path = self._db.get_tag_path(it.tag_id)
            tag_strings.append(path)
        # Also show fixed-field flags
        flags = []
        if record.favorite:
            flags.append("favorite")
        if record.to_delete:
            flags.append("to_delete")
        if record.reviewed:
            flags.append("reviewed")
        if flags:
            tag_strings.insert(0, "flags: " + ", ".join(flags))
        # Show DUP/KEEP status in dup review mode
        if self._source.is_dup_filtered and record.id:
            member = self._source.get_dup_member(record.id)
            if member:
                if member.is_kept:
                    tag_strings.append("status: KEEP")
                elif member.is_not_duplicate:
                    pass  # Not a duplicate, no label
                else:
                    tag_strings.append("status: DUP")
        single.info_overlay.set_tags(tag_strings)

    _COPY_TAG_ROOTS = {"scene", "event", "person"}

    def _copy_tags(self) -> None:
        """Copy scene, event, and person tags from the current image (Ctrl+C)."""
        records = self._get_selected_records()
        if not records:
            return
        record = records[0]
        if record.id is None:
            return

        image_tags = self._db.get_image_tags(record.id)
        # Filter to tags whose root category is scene, event, or person
        filtered = []
        for it in image_tags:
            path = self._db.get_tag_path(it.tag_id)
            root = path.split(".")[0]
            if root in self._COPY_TAG_ROOTS:
                filtered.append(it)

        self._copied_tags = filtered
        tag_names = [self._db.get_tag_path(t.tag_id) for t in filtered]
        self._status_bar.showMessage(
            f"Copied {len(filtered)} tag(s): {', '.join(tag_names)}"
            if filtered else "No scene/event/person tags to copy"
        )

    def _apply_tags_to_image(self, image_id: int) -> int:
        """Apply copied tags to an image, skipping those already present.

        Returns the number of new tags actually added.
        """
        existing = self._db.get_image_tags(image_id)
        existing_keys = {t.tag_id for t in existing}
        added = 0
        for tag in self._copied_tags:
            if tag.tag_id not in existing_keys:
                self._db.set_image_tag(image_id, tag.tag_id)
                added += 1
        return added

    def _paste_tags(self) -> None:
        """Paste copied tags onto the current image (Ctrl+V)."""
        if not self._copied_tags:
            self._status_bar.showMessage("No copied tags to paste")
            return

        records = self._get_selected_records()
        if not records:
            return

        img_count = 0
        tag_count = 0
        for record in records:
            if record.id is None:
                continue
            added = self._apply_tags_to_image(record.id)
            if added:
                tag_count += added
                img_count += 1

        self._update_overlay_tags()
        if tag_count:
            self._status_bar.showMessage(
                f"Pasted {tag_count} new tag(s) to {img_count} image(s)"
            )
        else:
            self._status_bar.showMessage("All tags already present")

    def _apply_tags_to_folder(self) -> None:
        """Apply copied tags to all images in the current folder or dup group (Ctrl+Shift+V)."""
        if not self._copied_tags:
            self._status_bar.showMessage("No copied tags to apply (use Ctrl+C first)")
            return

        records = self._get_selected_records()
        if not records:
            return
        record = records[0]
        if record.id is None:
            return

        img_count = 0
        tag_count = 0
        if self._source.is_dup_filtered:
            # Apply to all images in the current duplicate group
            for i in range(self._source.total):
                sibling = self._source.get_record(i)
                if sibling is None or sibling.id is None:
                    continue
                added = self._apply_tags_to_image(sibling.id)
                if added:
                    tag_count += added
                    img_count += 1
            label = "duplicate group"
        else:
            # Apply to all images in the same folder
            folder = Path(record.filepath).parent
            for i in range(self._source.total):
                sibling = self._source.get_record(i)
                if sibling is None or sibling.id is None:
                    continue
                if Path(sibling.filepath).parent != folder:
                    continue
                added = self._apply_tags_to_image(sibling.id)
                if added:
                    tag_count += added
                    img_count += 1
            label = "folder"

        self._update_overlay_tags()
        if tag_count:
            self._status_bar.showMessage(
                f"Applied {tag_count} new tag(s) to {img_count} image(s) in {label}"
            )
        else:
            self._status_bar.showMessage(f"All tags already present in {label}")

    def _mark_delete(self) -> None:
        """Mark selected images for deletion and advance."""
        records = self._get_selected_records()
        for record in records:
            if record.id is None:
                continue
            record.to_delete = True
            self._db.update_image(record)

        # In single view, advance to next image
        if self._view_manager.mode == ViewMode.SINGLE:
            self._view_manager.single_view.navigate_next()
        self._update_overlay_tags()
        self._update_status()

    def _unmark_delete(self) -> None:
        """Unmark selected images from deletion and advance."""
        records = self._get_selected_records()
        for record in records:
            if record.id is None:
                continue
            record.to_delete = False
            self._db.update_image(record)

        if self._view_manager.mode == ViewMode.SINGLE:
            self._view_manager.single_view.navigate_next()
        self._update_overlay_tags()
        self._update_status()

    def _mark_dup_group_delete(self) -> None:
        """Mark all non-kept DUP images in current group for deletion, advance."""
        if not self._source.is_dup_filtered:
            return

        marked = 0
        for i in range(self._source.total):
            record = self._source.get_record(i)
            if record is None or record.id is None:
                continue
            member = self._source.get_dup_member(record.id)
            if member is None:
                continue
            if member.is_kept or member.is_not_duplicate:
                continue
            record.to_delete = True
            self._db.update_image(record)
            marked += 1

        self._status_bar.showMessage(
            f"Marked {marked} duplicate(s) for deletion"
        )
        self._next_dup_group()

    def _unmark_dup_group_delete(self) -> None:
        """Unmark all images in current group from deletion, advance."""
        if not self._source.is_dup_filtered:
            return

        unmarked = 0
        for i in range(self._source.total):
            record = self._source.get_record(i)
            if record is None or record.id is None:
                continue
            if record.to_delete:
                record.to_delete = False
                self._db.update_image(record)
                unmarked += 1

        self._status_bar.showMessage(
            f"Unmarked {unmarked} image(s) from deletion"
        )
        self._next_dup_group()

    def _mark_delete_folder(self) -> None:
        """Mark all images in the current folder for deletion and advance."""
        records = self._get_selected_records()
        if not records:
            return
        folder = Path(records[0].filepath).parent

        for i in range(self._source.total):
            record = self._source.get_record(i)
            if record is None or record.id is None:
                continue
            if Path(record.filepath).parent == folder:
                record.to_delete = True
                self._db.update_image(record)

        # Navigate to next folder
        if self._view_manager.mode == ViewMode.SINGLE:
            self._view_manager.single_view.navigate_next_folder()
        self._update_overlay_tags()
        self._update_status()

    def _review_deletions(self) -> None:
        """Toggle delete-review filter on the image source."""
        if self._source.is_filtered:
            self._source.set_delete_filter(False)
            self._status_bar.showMessage("Exited deletion review")
        else:
            self._source.set_delete_filter(True)
            total = self._source.total
            if total == 0:
                self._source.set_delete_filter(False)
                self._status_bar.showMessage("No images marked for deletion")
                return
            # Switch to single view for review
            if self._view_manager.mode == ViewMode.GRID:
                self._view_manager.toggle_view()
            self._status_bar.showMessage(
                f"Reviewing {total} image(s) marked for deletion"
            )

    def _execute_deletions(self) -> None:
        """Delete all images marked for deletion from disk and database."""
        # Find all to_delete images from the full (unfiltered) record set
        all_records = self._db.get_all_images()
        to_delete = [r for r in all_records if r.to_delete and r.id is not None]

        if not to_delete:
            QMessageBox.information(
                self, "Delete", "No images marked for deletion."
            )
            return

        reply = QMessageBox.question(
            self, "Confirm Deletion",
            f"Delete {len(to_delete)} image(s) permanently?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted = 0
        dirs_to_check: set[Path] = set()
        db_dir = self._source._db_dir

        for record in to_delete:
            # Resolve path
            p = Path(record.filepath)
            if not p.is_absolute():
                p = db_dir / p
            dirs_to_check.add(p.parent)

            try:
                os.remove(p)
            except OSError:
                pass  # File may already be gone
            self._db.delete_image(record.id)
            deleted += 1

        # Remove empty directories
        for d in sorted(dirs_to_check, key=lambda x: len(x.parts), reverse=True):
            try:
                while d != db_dir and d.exists() and not any(d.iterdir()):
                    d.rmdir()
                    d = d.parent
            except OSError:
                pass

        # Turn off filter if active
        if self._source.is_filtered:
            self._source.set_delete_filter(False)

        self._source.refresh()
        self._update_status()
        self._status_bar.showMessage(f"Deleted {deleted} image(s)")

    def _show_tag_hotkeys(self) -> None:
        """Show an overlay listing configured tag hotkeys."""
        bindings = self._config.get("organizer.quick_toggle_bindings", {})
        entries = []
        if isinstance(bindings, dict):
            for key_str, actions in bindings.items():
                if isinstance(actions, str):
                    actions = [actions]
                if isinstance(actions, list):
                    entries.append((key_str, ", ".join(actions)))

        if not entries:
            entries.append(("(none)", "No hotkeys configured"))

        self._help.update_sections([("Tag Hotkeys", entries)])
        self._help.toggle()

    # --- Background hashing ---

    def _start_hashing(self) -> None:
        """Launch background hash computation for unhashed images."""
        if self._hash_thread and self._hash_thread.isRunning():
            return
        if not self._db.db_path:
            return
        self._hash_thread = HashThread(str(self._db.db_path), self)
        self._hash_thread.progress.connect(self._on_hash_progress)
        self._hash_thread.finished_hashing.connect(self._on_hash_finished)
        self._hash_thread.start()

    def _on_hash_progress(self, current: int, total: int, filepath: str) -> None:
        self._status_bar.showMessage(
            f"Hashing images... {current}/{total}"
        )

    def _on_hash_finished(self, hashed_count: int) -> None:
        if hashed_count > 0:
            self._status_bar.showMessage(
                f"Hashing complete: {hashed_count} image(s) hashed"
            )
            # Refresh DB records to pick up new hashes
            self._source.refresh()
        else:
            self._update_status()

    # --- Query filter ---

    def _show_query_dialog(self) -> None:
        """Open the query/filter dialog (F5)."""
        dialog = QueryDialog(
            self._db,
            initial_query=self._source.query_expression,
            parent=self,
        )
        if dialog.exec() == QueryDialog.DialogCode.Accepted:
            query = dialog.result_query
            if query is not None:
                self._source.apply_query(query)
                total = self._source.total
                self._status_bar.showMessage(
                    f"Filter active: {total} image(s) match"
                )
            else:
                self._source.clear_query()
                self._status_bar.showMessage("Filter cleared")
            self._update_status()

    # --- Duplicate management ---

    def _detect_duplicates(self) -> None:
        """Open duplicate detection dialog."""
        dialog = DuplicateDetectionDialog(
            self._db, config=self._config, parent=self
        )
        dialog.review_requested.connect(self._enter_dup_review)
        dialog.exec()

    def _toggle_dup_review(self) -> None:
        """Toggle duplicate review mode (F3)."""
        if self._source.is_dup_filtered:
            self._exit_dup_review()
        else:
            self._enter_dup_review()

    def _enter_dup_review(self) -> None:
        """Enter duplicate review mode, loading groups from DB."""
        # Save and clear any active query filter so dup mode sees all images
        self._saved_query = self._source.query_expression
        if self._saved_query:
            self._source.clear_query()
        self._source.set_dup_filter(True)
        if self._source.dup_group_count == 0:
            self._source.set_dup_filter(False)
            # Restore query if we cleared it
            if self._saved_query:
                self._source.apply_query(self._saved_query)
                self._saved_query = None
            self._status_bar.showMessage(
                "No duplicate groups found. Use Ctrl+Shift+D to detect."
            )
            return
        self._update_dup_status()
        self._update_dup_grid_labels()

    def _exit_dup_review(self) -> None:
        """Exit duplicate review mode."""
        self._source.set_dup_filter(False)
        self._view_manager.grid_view.set_dup_labels({})
        # Restore saved query filter
        if self._saved_query:
            self._source.apply_query(self._saved_query)
            self._saved_query = None
        self._status_bar.showMessage("Exited duplicate review")

    def _next_dup_group(self) -> None:
        """Navigate to next duplicate group."""
        if not self._source.is_dup_filtered:
            return
        idx = self._source.current_dup_group_index
        if idx < self._source.dup_group_count - 1:
            self._source.set_dup_group(idx + 1)
        else:
            self._source.set_dup_group(0)  # Wrap around
        self._update_dup_status()
        self._update_dup_grid_labels()

    def _prev_dup_group(self) -> None:
        """Navigate to previous duplicate group."""
        if not self._source.is_dup_filtered:
            return
        idx = self._source.current_dup_group_index
        if idx > 0:
            self._source.set_dup_group(idx - 1)
        else:
            self._source.set_dup_group(self._source.dup_group_count - 1)
        self._update_dup_status()
        self._update_dup_grid_labels()

    def _toggle_not_duplicate(self) -> None:
        """Toggle is_not_duplicate flag on current image (Ctrl+N)."""
        if not self._source.is_dup_filtered:
            return
        records = self._get_selected_records()
        if not records:
            return
        record = records[0]
        if record.id is None:
            return
        member = self._source.get_dup_member(record.id)
        if member is None:
            return
        new_val = not member.is_not_duplicate
        self._db.update_duplicate_member(
            member.id, is_not_duplicate=new_val
        )
        self._source.reload_dup_groups()
        self._update_overlay_tags()
        self._update_dup_grid_labels()

    def _keep_image(self) -> None:
        """Toggle kept status on current image (Ctrl+K)."""
        if not self._source.is_dup_filtered:
            return
        records = self._get_selected_records()
        if not records:
            return
        record = records[0]
        if record.id is None:
            return
        group = self._source.current_dup_group
        if group is None:
            return
        member = self._source.get_dup_member(record.id)
        if member is None:
            return
        if member.is_kept:
            # Toggle off
            self._db.update_duplicate_member(member.id, is_kept=False)
        else:
            # Clear is_kept on all others, then set on current
            for m in group.members:
                if m.is_kept:
                    self._db.update_duplicate_member(m.id, is_kept=False)
            self._db.update_duplicate_member(member.id, is_kept=True)
        self._source.reload_dup_groups()
        self._update_overlay_tags()
        self._update_dup_grid_labels()

    def _delete_unmarked_dups(self) -> None:
        """Delete images not marked as kept or not-duplicate in current group."""
        if not self._source.is_dup_filtered:
            return
        group = self._source.current_dup_group
        if group is None:
            return

        # Find the kept image and images to delete
        kept_member = None
        to_delete_members = []
        for m in group.members:
            if m.is_kept:
                kept_member = m
            elif not m.is_not_duplicate:
                to_delete_members.append(m)

        if not to_delete_members:
            self._status_bar.showMessage("No unmarked duplicates to delete")
            return

        if kept_member is None:
            QMessageBox.warning(
                self, "No Kept Image",
                "Mark one image as kept (Ctrl+K) before deleting duplicates."
            )
            return

        reply = QMessageBox.question(
            self, "Delete Duplicates",
            f"Delete {len(to_delete_members)} duplicate image(s)?\n"
            "Tags will be transferred to the kept image.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Transfer tags from deleted images to kept image
        kept_tags = {
            t.tag_id
            for t in self._db.get_image_tags(kept_member.image_id)
        }
        for m in to_delete_members:
            for tag in self._db.get_image_tags(m.image_id):
                if tag.tag_id not in kept_tags:
                    self._db.set_image_tag(
                        kept_member.image_id, tag.tag_id
                    )
                    kept_tags.add(tag.tag_id)

        # Delete the files and DB records
        db_dir = self._source._db_dir
        deleted = 0
        for m in to_delete_members:
            record = None
            for r in self._db.get_all_images():
                if r.id == m.image_id:
                    record = r
                    break
            if record:
                p = Path(record.filepath)
                if not p.is_absolute():
                    p = db_dir / p
                try:
                    os.remove(p)
                except OSError:
                    pass
            self._db.delete_image(m.image_id)
            deleted += 1

        # Clean up group if 1 or fewer members remain
        remaining = [
            m for m in group.members
            if m not in to_delete_members
        ]
        if len(remaining) <= 1:
            self._db.delete_duplicate_group(group.id)

        # Refresh and advance
        self._source.refresh()
        self._source.reload_dup_groups()

        if self._source.dup_group_count == 0:
            self._exit_dup_review()
            self._status_bar.showMessage(
                f"Deleted {deleted} duplicate(s). No more groups to review."
            )
        else:
            self._update_dup_status()
            self._update_dup_grid_labels()
            self._status_bar.showMessage(
                f"Deleted {deleted} duplicate(s)"
            )

    def _update_dup_status(self) -> None:
        """Update status bar with current dup group info."""
        idx = self._source.current_dup_group_index + 1
        total = self._source.dup_group_count
        count = self._source.total
        self._status_bar.showMessage(
            f"Duplicate group {idx}/{total} ({count} images)"
        )

    def _update_dup_grid_labels(self) -> None:
        """Update DUP/KEEP labels on grid view thumbnails."""
        if not self._source.is_dup_filtered:
            self._view_manager.grid_view.set_dup_labels({})
            return
        group = self._source.current_dup_group
        if group is None:
            return
        labels: dict[int, str] = {}
        for i in range(self._source.total):
            record = self._source.get_record(i)
            if record and record.id:
                member = self._source.get_dup_member(record.id)
                if member:
                    if member.is_kept:
                        labels[i] = "KEEP"
                    elif member.is_not_duplicate:
                        labels[i] = ""
                    else:
                        labels[i] = "DUP"
        self._view_manager.grid_view.set_dup_labels(labels)

    def _update_status(self) -> None:
        db_name = (
            Path(self._db.db_path).name if self._db.db_path else "No DB"
        )
        mode = self._view_manager.mode.capitalize()
        total = self._source.total
        query_status = "  |  FILTERED" if self._source.query_expression else ""
        self._status_bar.showMessage(
            f"DB: {db_name}  |  {total} images  |  {mode} view{query_status}"
        )

    def _save_with_rotation(self) -> None:
        """Save the current image with rotation baked into the file (Ctrl+Shift+S)."""
        if self._view_manager.mode != ViewMode.SINGLE:
            self._status_bar.showMessage("Save with rotation only works in single view")
            return

        single = self._view_manager.single_view
        rotation = single.canvas.rotation
        if rotation == 0:
            self._status_bar.showMessage("No rotation to save")
            return

        idx = single.current_index
        filepath = self._source.get_filepath(idx)
        if not filepath or not os.path.isfile(filepath):
            self._status_bar.showMessage("Cannot save: file not found")
            return

        from PIL import Image
        from photo_manager.scanner.exif import get_oriented_image
        from photo_manager.hashing.hasher import compute_hashes
        import tempfile

        try:
            # Open with EXIF correction already applied
            img = get_oriented_image(filepath)

            # Apply the user's rotation
            pil_rotation = {
                90: Image.Transpose.ROTATE_270,   # 90° CW display = 270° CCW PIL
                180: Image.Transpose.ROTATE_180,
                270: Image.Transpose.ROTATE_90,    # 270° CW display = 90° CCW PIL
            }
            transform = pil_rotation.get(rotation)
            if transform:
                img = img.transpose(transform)

            # Determine save parameters based on format
            suffix = Path(filepath).suffix.lower()
            save_kwargs: dict = {}
            if suffix in (".jpg", ".jpeg"):
                save_kwargs["format"] = "JPEG"
                save_kwargs["quality"] = 95
                save_kwargs["subsampling"] = 0  # 4:4:4
            elif suffix == ".png":
                save_kwargs["format"] = "PNG"
            elif suffix == ".webp":
                save_kwargs["format"] = "WEBP"
                save_kwargs["quality"] = 95
            elif suffix == ".bmp":
                save_kwargs["format"] = "BMP"
            elif suffix == ".tiff" or suffix == ".tif":
                save_kwargs["format"] = "TIFF"

            # Preserve EXIF data but reset orientation to normal (JPEG/TIFF only)
            if suffix in (".jpg", ".jpeg", ".tiff", ".tif"):
                original_img = Image.open(filepath)
                exif_data = original_img.getexif()
                if exif_data:
                    exif_data[0x0112] = 1  # Orientation = Normal
                    save_kwargs["exif"] = exif_data.tobytes()
                original_img.close()

            # Capture dimensions before closing
            new_w, new_h = img.size

            # Safe write: temp file in same directory, then atomic replace
            directory = os.path.dirname(filepath)
            fd, tmp_path = tempfile.mkstemp(
                suffix=suffix, dir=directory, prefix=".save_rot_"
            )
            os.close(fd)
            try:
                img.save(tmp_path, **save_kwargs)
                img.close()
                os.replace(tmp_path, filepath)
            except Exception:
                img.close()
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                raise

            # Update DB record: dimensions and hashes changed
            record = self._source.get_record(idx)
            if record and record.id is not None:
                record.width = new_w
                record.height = new_h
                # Recompute hashes since pixel data changed
                hashes = compute_hashes(filepath)
                if hashes:
                    record.phash_0 = hashes.phash_0
                    record.phash_90 = hashes.phash_90
                    record.phash_180 = hashes.phash_180
                    record.phash_270 = hashes.phash_270
                    record.dhash_0 = hashes.dhash_0
                    record.dhash_90 = hashes.dhash_90
                    record.dhash_180 = hashes.dhash_180
                    record.dhash_270 = hashes.dhash_270
                    record.phash_hmirror = hashes.phash_hmirror
                    record.dhash_hmirror = hashes.dhash_hmirror
                self._db.update_image(record)

            # Evict cached pixmap and reload the image from disk
            if single._loader:
                single._loader.invalidate(idx)
            # Also invalidate grid thumbnail so it reflects the rotation
            grid = self._view_manager.grid_view
            grid._thumb_worker.invalidate(idx, filepath)
            single.canvas._rotation = 0
            single.goto(idx)
            self._status_bar.showMessage(
                f"Saved with {rotation}° rotation: {Path(filepath).name}"
            )

        except Exception as e:
            self._status_bar.showMessage(f"Save failed: {e}")

    def eventFilter(self, obj, event: QEvent) -> bool:
        """Catch keys at the application level before child widgets consume them."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key == Qt.Key.Key_Tab:
                if self._key_handler.handle_key_event(event):
                    return True
            # Catch Alt+Left/Right before QScrollArea consumes them
            if (key in (Qt.Key.Key_Left, Qt.Key.Key_Right)
                    and mods & Qt.KeyboardModifier.AltModifier):
                if self._key_handler.handle_key_event(event):
                    return True
            # Catch Alt+Period for unmark-delete
            if (key == Qt.Key.Key_Period
                    and mods & Qt.KeyboardModifier.AltModifier):
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
        if self._hash_thread and self._hash_thread.isRunning():
            self._hash_thread.cancel()
            self._hash_thread.wait()
        self._config.save_session()
        self._view_manager.shutdown()
        self._db.close()
        super().closeEvent(event)
