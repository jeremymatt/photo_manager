"""Application entry point for the photo organizer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QFileDialog

from photo_manager.config.config import ConfigManager, get_db_config_path
from photo_manager.db.manager import DatabaseManager
from photo_manager.organizer.organizer_window import OrganizerWindow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="photo-organizer",
        description="Photo Manager - Full Desktop Organizer",
    )
    parser.add_argument(
        "db_path", nargs="?", default=None,
        help="Path to database file (opens or creates)",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to database file (alias for positional arg)",
    )
    parser.add_argument(
        "--import", dest="import_dir", type=str, default=None,
        help="Directory to import on startup",
    )
    parser.add_argument(
        "--view", choices=["grid", "single"], default=None,
        help="Start in grid or single-image view",
    )
    parser.add_argument(
        "--fullscreen", action="store_true", default=None,
        help="Start in fullscreen mode",
    )
    parser.add_argument(
        "--windowed", action="store_true", default=None,
        help="Start in windowed mode",
    )
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config YAML file",
    )
    return parser.parse_args(argv)


def create_organizer_app(argv: list[str] | None = None) -> int:
    """Create and run the organizer application. Returns exit code."""
    args = parse_args(argv)

    app = QApplication(sys.argv)
    app.setApplicationName("Photo Manager Organizer")

    # Config — basic load first to get last_db_path if needed
    config = ConfigManager()
    if args.config:
        config.load(args.config)

    # Determine fullscreen
    fullscreen = None
    if args.fullscreen:
        fullscreen = True
    elif args.windowed:
        fullscreen = False

    # Database
    db = DatabaseManager()
    db_path = args.db_path or args.db or config.get("organizer.last_db_path")

    if db_path:
        if Path(db_path).exists():
            db.open_database(db_path)
        else:
            db.create_database(db_path)
    else:
        # Show file browser to open an existing database
        db_path, _ = QFileDialog.getOpenFileName(
            None,
            "Open Database",
            "",
            "Database files (*.db);;All files (*)",
        )
        if not db_path:
            return 0
        db.open_database(db_path)

    config.set("organizer.last_db_path", db_path)

    # Reload config with per-DB layering (DEFAULT <- db_config <- cli_config)
    db_config_path = get_db_config_path(db_path)
    config.load_layered(
        db_config_path=db_config_path,
        cli_config_path=args.config,
    )

    # Create main window
    window = OrganizerWindow(
        db=db,
        config=config,
        import_dir=args.import_dir,
        start_view=args.view,
        start_fullscreen=fullscreen,
    )
    window.show()

    return app.exec()
