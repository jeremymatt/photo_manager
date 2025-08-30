"""
Main entry point for the photo manager application.
Routes between Qt main application and Pi slideshow based on arguments.
"""

import sys
import os
import argparse
from pathlib import Path

# Add the package to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Main entry point with argument parsing and application routing."""
    parser = argparse.ArgumentParser(
        description='Photo Manager - Fast Image Viewer & File Manager',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /photos                              # Open Qt viewer
  %(prog)s --slideshow /photos                  # Qt slideshow mode  
  %(prog)s --pi-slideshow /photos               # Lightweight Pi slideshow
  %(prog)s --scan /new_photos                   # Scan directory only
  %(prog)s --export-query "favorites:true" --export-path /backup
        """
    )
    
    # Basic arguments
    parser.add_argument('directory', nargs='?', help='Directory containing photos')
    parser.add_argument('--config', help='Path to configuration file')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    
    # Application mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument('--slideshow', action='store_true', 
                           help='Start in Qt slideshow mode')
    mode_group.add_argument('--pi-slideshow', action='store_true',
                           help='Start lightweight Pi slideshow (tkinter)')
    mode_group.add_argument('--scan', metavar='DIR', 
                           help='Scan directory and add to database only')
    
    # Database operations
    parser.add_argument('--init-db', action='store_true',
                       help='Initialize database in directory')
    parser.add_argument('--check-db', action='store_true',
                       help='Check database for errors')
    parser.add_argument('--repair', action='store_true',
                       help='Repair database issues')
    parser.add_argument('--clean-missing', action='store_true',
                       help='Remove missing files from database')
    
    # Export operations
    parser.add_argument('--export-query', help='Query for images to export')
    parser.add_argument('--export-path', help='Export destination directory')
    parser.add_argument('--export-structure', default='{year}/{event_tag}',
                       help='Export directory structure template')
    parser.add_argument('--export-preview', action='store_true',
                       help='Preview export without executing')
    parser.add_argument('--export-copy', action='store_true',
                       help='Copy files during export (default)')
    parser.add_argument('--export-move', action='store_true', 
                       help='Move files during export')
    parser.add_argument('--export-db', action='store_true',
                       help='Create subset database with exported images')
    
    # Auto-tagging
    parser.add_argument('--auto-tag-template', help='Path to auto-tagging template')
    parser.add_argument('--no-auto-tag', action='store_true',
                       help='Skip auto-tagging (EXIF only)')
    
    # Slideshow specific
    parser.add_argument('--slideshow-duration', type=float, 
                       help='Duration per image in seconds')
    parser.add_argument('--slideshow-random', action='store_true',
                       help='Random slideshow order')
    parser.add_argument('--query', help='Query to filter displayed images')
    
    # UI options
    parser.add_argument('--fullscreen', action='store_true',
                       help='Start in fullscreen mode')
    parser.add_argument('--no-fullscreen', action='store_true',
                       help='Start in windowed mode')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.directory and not args.scan and not args.export_query:
        parser.error("Must specify directory or operation")
    
    if args.export_query and not args.export_path:
        parser.error("--export-query requires --export-path")
    
    # Route to appropriate application
    try:
        if args.pi_slideshow:
            return run_pi_slideshow(args)
        elif args.scan:
            return run_scan_only(args)
        elif args.export_query:
            return run_export(args)
        elif args.init_db or args.check_db or args.clean_missing:
            return run_database_operations(args)
        else:
            return run_qt_application(args)
            
    except KeyboardInterrupt:
        print("\nOperation interrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def run_pi_slideshow(args):
    """Run the lightweight Pi slideshow."""
    try:
        from photo_manager.ui.tkinter.pi_slideshow import PiSlideshow
        
        if not args.directory:
            print("Error: Directory required for slideshow")
            return 1
        
        slideshow = PiSlideshow(
            directory_path=args.directory,
            db_path=args.db,
            config_path=args.config,
            query=args.query
        )
        
        # Apply command line overrides
        if args.slideshow_duration:
            slideshow.slideshow_config['duration'] = args.slideshow_duration
        if args.slideshow_random:
            slideshow.slideshow_config['random_order'] = True
        
        slideshow.start_slideshow()
        return 0
        
    except ImportError as e:
        print(f"Error: Required dependencies not available: {e}")
        return 1


def run_qt_application(args):
    """Run the main Qt application."""
    try:
        # Import Qt modules
        from photo_manager.ui.qt.viewer import MainWindow
        from PySide2.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        
        window = MainWindow(
            directory_path=args.directory,
            db_path=args.db,
            config_path=args.config,
            slideshow_mode=args.slideshow,
            query=args.query
        )
        
        # Apply command line overrides
        if args.fullscreen:
            window.showFullScreen()
        elif args.no_fullscreen:
            window.showNormal()
        else:
            # Use config default
            window.show()
        
        return app.exec_()
        
    except ImportError as e:
        print(f"Error: Qt dependencies not available: {e}")
        print("Try installing with: pip install PySide2")
        return 1


def run_scan_only(args):
    """Run directory scan without starting viewer."""
    from photo_manager.database.database_manager import DatabaseManager
    from photo_manager.core.file_scanner import FileScanner
    from photo_manager.config.config_manager import ConfigManager
    
    try:
        scan_dir = args.scan
        
        if not os.path.exists(scan_dir):
            print(f"Error: Directory does not exist: {scan_dir}")
            return 1
        
        # Load configuration
        config_manager = ConfigManager(args.config)
        config = config_manager.load_config(scan_dir)
        
        # Initialize database
        db_config = config['database'].copy()
        if args.db:
            db_config['path'] = args.db
        else:
            db_config['path'] = os.path.join(scan_dir, '.photo_manager.db')
        
        db_manager = DatabaseManager(db_config)
        if not db_manager.initialize_connection():
            print("Error: Failed to initialize database")
            return 1
        
        # Load auto-tag template if specified
        auto_tag_template = None
        if not args.no_auto_tag:
            template_data = config_manager.load_auto_tag_template(
                args.auto_tag_template, scan_dir
            )
            if template_data:
                from photo_manager.config.config_manager import AutoTagTemplate
                auto_tag_template = AutoTagTemplate(template_data)
        
        # Scan directory
        scanner = FileScanner(db_manager, config)
        
        def progress_callback(processed, total, current_file):
            print(f"Scanning: {processed}/{total} - {current_file}")
        
        added, skipped, errors = scanner.scan_directory(
            scan_dir, auto_tag_template, progress_callback
        )
        
        print(f"\nScan complete:")
        print(f"  Added: {added} images")
        print(f"  Skipped: {skipped} images")
        print(f"  Errors: {len(errors)} images")
        
        if errors and args.verbose:
            print("\nError files:")
            for error_file in errors:
                print(f"  {error_file}")
        
        return 0
        
    except Exception as e:
        print(f"Error during scan: {e}")
        return 1


def run_export(args):
    """Run export operation."""
    from photo_manager.database.database_manager import DatabaseManager
    from photo_manager.core.tag_manager import TagManager
    from photo_manager.core.export_manager import ExportManager
    from photo_manager.config.config_manager import ConfigManager
    
    try:
        # Load configuration
        config_manager = ConfigManager(args.config)
        
        # Use directory from export path for config if no directory specified
        config_dir = args.directory or os.path.dirname(args.export_path)
        config = config_manager.load_config(config_dir)
        
        # Initialize database
        db_config = config['database'].copy()
        if args.db:
            db_config['path'] = args.db
        elif args.directory:
            db_config['path'] = os.path.join(args.directory, '.photo_manager.db')
        else:
            print("Error: Database path required for export")
            return 1
        
        db_manager = DatabaseManager(db_config)
        if not db_manager.initialize_connection():
            print("Error: Failed to connect to database")
            return 1
        
        # Initialize managers
        tag_manager = TagManager(db_manager)
        export_manager = ExportManager(db_manager, tag_manager, config)
        
        with db_manager.get_session() as session:
            if args.export_preview:
                # Show preview only
                preview = export_manager.preview_export(
                    session, args.export_query, args.export_structure, args.export_path
                )
                
                from photo_manager.core.export_manager import ExportPreview
                preview_analyzer = ExportPreview(export_manager)
                
                print(preview_analyzer.generate_summary_report(preview))
                
                return 0
            
            else:
                # Perform actual export
                operation = 'move' if args.export_move else 'copy'
                
                def progress_callback(processed, total, current_file):
                    print(f"Exporting: {processed}/{total} - {current_file}")
                
                result = export_manager.export_images(
                    session=session,
                    query=args.export_query,
                    export_path=args.export_path,
                    structure_template=args.export_structure,
                    operation=operation,
                    export_database=args.export_db,
                    progress_callback=progress_callback
                )
                
                if result['success']:
                    print(f"\nExport complete:")
                    print(f"  Exported: {result['exported_count']}/{result['total_images']} images")
                    if result.get('subset_database'):
                        print(f"  Subset database: {result['subset_database']}")
                    
                    if result['errors'] and args.verbose:
                        print("\nErrors:")
                        for error in result['errors']:
                            print(f"  {error['image']}: {error['error']}")
                    
                    return 0
                else:
                    print(f"Export failed: {result.get('message', 'Unknown error')}")
                    return 1
        
    except Exception as e:
        print(f"Error during export: {e}")
        return 1


def run_database_operations(args):
    """Run database maintenance operations."""
    from photo_manager.database.database_manager import DatabaseManager, create_database
    from photo_manager.config.config_manager import ConfigManager
    
    try:
        directory = args.directory or os.getcwd()
        
        # Load configuration
        config_manager = ConfigManager(args.config)
        config = config_manager.load_config(directory)
        
        # Database configuration
        db_config = config['database'].copy()
        if args.db:
            db_config['path'] = args.db
        else:
            db_config['path'] = os.path.join(directory, '.photo_manager.db')
        
        if args.init_db:
            # Initialize new database
            if create_database(db_config['path']):
                print(f"Database initialized: {db_config['path']}")
                
                # Create default config files
                if config_manager.save_config(directory):
                    print(f"Default configuration created in {directory}")
                
                return 0
            else:
                print("Failed to initialize database")
                return 1
        
        # For other operations, database must exist
        if not os.path.exists(db_config['path']):
            print(f"Error: Database not found: {db_config['path']}")
            print("Use --init-db to create a new database")
            return 1
        
        db_manager = DatabaseManager(db_config)
        if not db_manager.initialize_connection():
            print("Error: Failed to connect to database")
            return 1
        
        if args.clean_missing:
            with db_manager.get_session() as session:
                removed = db_manager.remove_missing_files(session)
                print(f"Removed {removed} missing files from database")
        
        if args.check_db:
            with db_manager.get_session() as session:
                stats = db_manager.get_statistics(session)
                
                print("Database Statistics:")
                print(f"  Total images: {stats['total_images']}")
                print(f"  Corrupt images: {stats['corrupt_images']}")
                print(f"  Reviewed images: {stats['reviewed_images']}")
                print(f"  Total tags: {stats['total_tags']}")
                print(f"  Directories scanned: {stats['directories']}")
        
        return 0
        
    except Exception as e:
        print(f"Error during database operation: {e}")
        return 1


def check_dependencies():
    """Check if required dependencies are available."""
    missing_deps = []
    
    try:
        import PIL
    except ImportError:
        missing_deps.append('Pillow')
    
    try:
        import sqlalchemy
    except ImportError:
        missing_deps.append('SQLAlchemy')
    
    try:
        import yaml
    except ImportError:
        missing_deps.append('PyYAML')
    
    try:
        import imagehash
    except ImportError:
        missing_deps.append('imagehash')
    
    if missing_deps:
        print("Error: Missing required dependencies:")
        for dep in missing_deps:
            print(f"  {dep}")
        print("\nInstall with: pip install -r requirements.txt")
        return False
    
    return True


def setup_logging(verbose: bool):
    """Setup logging configuration."""
    import logging
    
    level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


if __name__ == '__main__':
    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)
    
    # Run main application
    sys.exit(main())