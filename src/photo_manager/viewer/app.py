"""Application entry point for the lightweight photo viewer.

Usage:
    python -m photo_manager.viewer.app <path> [options]

    <path> can be:
        - A directory: recursively scan for images
        - A .photo_manager.db file: load from database

Options:
    --config <path>     Config YAML file
    --slideshow         Start in slideshow mode
    --fullscreen        Start in fullscreen
    --windowed          Start in windowed mode
    --query             Open query dialog (DB mode only)
    --query "expr"      Apply query filter directly (DB mode only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from photo_manager.config.config import ConfigManager
from photo_manager.db.manager import DatabaseManager
from photo_manager.query.engine import QueryEngine
from photo_manager.viewer.image_loader import collect_image_files
from photo_manager.viewer.main_window import MainWindow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lightweight photo viewer",
        prog="photo-viewer",
    )
    parser.add_argument(
        "path",
        help="Directory of images or .photo_manager.db file",
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to config YAML file",
        default=None,
    )
    parser.add_argument(
        "--slideshow", "-s",
        action="store_true",
        help="Start in slideshow mode",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        default=None,
        help="Start in fullscreen mode",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Start in windowed mode",
    )
    parser.add_argument(
        "--query", "-q",
        nargs="?",
        const="",  # --query with no value → empty string → open dialog
        default=None,  # --query not provided → None → all images
        help='Filter query expression (DB mode). Use --query without value to open dialog.',
    )
    return parser


def load_file_list(
    target_path: Path,
    config: ConfigManager,
    query_arg: str | None,
) -> list[str]:
    """Build the file list from a directory or database."""

    # Database mode
    if target_path.suffix in (".db", ".sqlite", ".sqlite3") or target_path.name == ".photo_manager.db":
        db = DatabaseManager()
        db.open_database(target_path)
        db_dir = target_path.parent.resolve()

        # Determine if we need to filter
        if query_arg is not None and query_arg != "":
            # Direct query expression provided
            engine = QueryEngine(db)
            images = engine.query(query_arg)
        elif query_arg == "":
            # --query flag with no value → show dialog
            app_temp = QApplication.instance()
            if app_temp is None:
                app_temp = QApplication(sys.argv)

            from photo_manager.viewer.query_dialog import QueryDialog
            dialog = QueryDialog(db)
            if dialog.exec():
                result_query = dialog.result_query
                if result_query:
                    engine = QueryEngine(db)
                    images = engine.query(result_query)
                else:
                    images = db.get_all_images()
            else:
                # User cancelled
                db.close()
                return []
        else:
            # No --query flag → all images
            images = db.get_all_images()

        file_list = []
        for img in images:
            abs_path = db_dir / img.filepath
            if abs_path.exists():
                file_list.append(str(abs_path))
        db.close()
        return sorted(file_list)

    # Directory mode
    if target_path.is_dir():
        recursive = config.get("file_scanning.include_subdirectories", True)
        return collect_image_files(target_path, recursive=recursive)

    # Single file
    if target_path.is_file():
        return [str(target_path)]

    print(f"Error: '{target_path}' is not a valid directory, database, or image file.")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    target_path = Path(args.path).resolve()
    if not target_path.exists():
        print(f"Error: '{args.path}' does not exist.")
        return 1

    # Load config
    config = ConfigManager()
    if args.config:
        config_path = Path(args.config)
        if config_path.exists():
            config.load(config_path)

    # Build file list
    file_list = load_file_list(target_path, config, args.query)
    if not file_list:
        print("No images found.")
        return 1

    # Determine fullscreen
    fullscreen = None
    if args.fullscreen:
        fullscreen = True
    elif args.windowed:
        fullscreen = False

    # Create/get QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = MainWindow(
        file_list=file_list,
        config=config,
        start_slideshow=args.slideshow,
        start_fullscreen=fullscreen,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
