"""Unified launcher for viewer/organizer with directory-based heuristics."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from photo_manager.organizer.app import create_organizer_app
from photo_manager.viewer.app import main as viewer_main

DB_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}
IMPORT_SENTINEL = "__USE_TARGET__"


def _looks_like_db_path(path: Path) -> bool:
    return path.suffix.lower() in DB_EXTENSIONS


def _find_db_files(directory: Path) -> list[Path]:
    db_files = [
        p for p in directory.iterdir()
        if p.is_file() and _looks_like_db_path(p)
    ]
    return sorted(db_files, key=lambda p: p.name.lower())


def _prompt_select_db(db_files: list[Path]) -> Path | None:
    print("Multiple database files found:")
    for idx, db_file in enumerate(db_files, start=1):
        print(f"  {idx}. {db_file.name}")
    while True:
        choice = input("Select a database by number (or press Enter to cancel): ").strip()
        if choice == "":
            return None
        if choice.isdigit():
            selected = int(choice)
            if 1 <= selected <= len(db_files):
                return db_files[selected - 1]
        print("Invalid selection.")


def _append_flag(args: list[str], flag: str, value: str | None = None) -> None:
    if value is None:
        args.append(flag)
    else:
        args.extend([flag, value])


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p_man",
        description="Photo Manager launcher (auto-selects viewer or organizer)",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Target directory or file (default: current directory)",
    )
    parser.add_argument(
        "--import",
        dest="import_dir",
        nargs="?",
        const=IMPORT_SENTINEL,
        default=argparse.SUPPRESS,
        help="Import the target directory (optional: specify a directory)",
    )
    parser.add_argument(
        "--db",
        dest="db",
        default=argparse.SUPPRESS,
        help="Database file path",
    )
    parser.add_argument(
        "--view",
        choices=["grid", "single"],
        default=argparse.SUPPRESS,
        help="Organizer start view",
    )
    parser.add_argument(
        "--config",
        dest="config",
        default=argparse.SUPPRESS,
        help="Config YAML file",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Start fullscreen",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Start windowed",
    )
    parser.add_argument(
        "--slideshow",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Start slideshow (viewer)",
    )
    parser.add_argument(
        "--query",
        nargs="?",
        const="",
        default=argparse.SUPPRESS,
        help="Viewer query filter (use without value to open dialog)",
    )
    return parser


def _resolve_target_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg).expanduser().resolve()
    return Path.cwd().resolve()


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args, unknown = parser.parse_known_args(argv)
    argd = vars(args)

    path_arg = argd.get("path")
    target_path = _resolve_target_path(path_arg)

    import_dir: Path | None = None
    if "import_dir" in argd:
        if argd["import_dir"] == IMPORT_SENTINEL:
            import_dir = target_path
        else:
            import_dir = Path(argd["import_dir"]).expanduser().resolve()
            if path_arg is None:
                target_path = import_dir

    path_arg_is_db = path_arg is not None and _looks_like_db_path(Path(path_arg))

    if import_dir is not None:
        if not import_dir.exists() or not import_dir.is_dir():
            print(f"Error: import directory '{import_dir}' does not exist or is not a directory.")
            return 1

    db_path: Path | None = None
    if "db" in argd:
        db_path = Path(argd["db"]).expanduser().resolve()
    elif path_arg_is_db:
        db_path = Path(path_arg).expanduser().resolve()
    elif target_path.exists() and target_path.is_dir():
        db_files = _find_db_files(target_path)
        if len(db_files) == 1:
            db_path = db_files[0]
        elif len(db_files) > 1:
            db_path = _prompt_select_db(db_files)
            if db_path is None:
                return 0

    use_organizer = (
        "db" in argd
        or "view" in argd
        or import_dir is not None
        or db_path is not None
        or path_arg_is_db
    )

    if use_organizer:
        organizer_args: list[str] = []

        if db_path is not None:
            _append_flag(organizer_args, "--db", str(db_path))

        if import_dir is not None:
            _append_flag(organizer_args, "--import", str(import_dir))

        if "view" in argd:
            _append_flag(organizer_args, "--view", argd["view"])
        elif db_path is not None:
            _append_flag(organizer_args, "--view", "single")

        if "fullscreen" in argd:
            _append_flag(organizer_args, "--fullscreen")
        if "windowed" in argd:
            _append_flag(organizer_args, "--windowed")
        if "config" in argd:
            _append_flag(organizer_args, "--config", argd["config"])

        organizer_args.extend(unknown)
        return create_organizer_app(organizer_args)

    # Viewer path validation
    if not target_path.exists():
        print(f"Error: '{target_path}' does not exist.")
        return 1

    viewer_args: list[str] = [str(target_path)]
    if "config" in argd:
        _append_flag(viewer_args, "--config", argd["config"])
    if "slideshow" in argd:
        _append_flag(viewer_args, "--slideshow")
    if "fullscreen" in argd:
        _append_flag(viewer_args, "--fullscreen")
    if "windowed" in argd:
        _append_flag(viewer_args, "--windowed")
    if "query" in argd:
        _append_flag(viewer_args, "--query")
        if argd["query"] != "":
            viewer_args.append(argd["query"])

    viewer_args.extend(unknown)
    return viewer_main(viewer_args)


if __name__ == "__main__":
    raise SystemExit(main())
