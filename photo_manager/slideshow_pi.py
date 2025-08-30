#!/usr/bin/env python3
"""
Standalone entry point for the Pi slideshow.
Lightweight slideshow viewer for Raspberry Pi digital picture frames.
"""

import sys
import os
import argparse

# Add the package to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Main entry point for Pi slideshow."""
    parser = argparse.ArgumentParser(
        description='Lightweight Pi Slideshow for Digital Picture Frames'
    )
    
    parser.add_argument('directory', help='Directory containing photos')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--query', help='Query to filter images')
    parser.add_argument('--duration', type=float, default=5.0,
                       help='Duration per image in seconds')
    parser.add_argument('--transition', choices=['fade', 'wipe', 'replace'], 
                       default='fade', help='Transition effect')
    parser.add_argument('--random', action='store_true', help='Random order')
    parser.add_argument('--info', action='store_true', help='Show image info')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    try:
        # Check if directory exists
        if not os.path.exists(args.directory):
            print(f"Error: Directory does not exist: {args.directory}")
            return 1
        
        # Check for required dependencies (minimal set)
        missing_deps = []
        try:
            import tkinter as tk
        except ImportError:
            missing_deps.append('tkinter')
            
        try:
            from PIL import Image, ImageTk
        except ImportError:
            missing_deps.append('Pillow')
            
        try:
            import yaml
        except ImportError:
            missing_deps.append('PyYAML')
            
        try:
            import sqlalchemy
        except ImportError:
            missing_deps.append('SQLAlchemy')
        
        if missing_deps:
            print(f"Error: Required dependencies not available: {', '.join(missing_deps)}")
            print("Install with: pip install -r requirements.txt")
            return 1
        
        # Import slideshow module
        from photo_manager.ui.tkinter.pi_slideshow import PiSlideshow
        
        # Create slideshow instance
        slideshow = PiSlideshow(
            directory_path=args.directory,
            db_path=args.db,
            config_path=args.config,
            query=args.query
        )
        
        # Apply command line overrides
        if args.duration:
            slideshow.slideshow_config['duration'] = args.duration
        if args.transition:
            slideshow.slideshow_config['transition'] = args.transition
        if args.random:
            slideshow.slideshow_config['random_order'] = True
        if args.info:
            slideshow.slideshow_config['show_info'] = True
        
        print(f"Starting Pi slideshow with {len(slideshow.images)} images")
        print(f"Duration: {slideshow.slideshow_config['duration']}s per image")
        print(f"Transition: {slideshow.slideshow_config['transition']}")
        print("\nControls:")
        print("  Space: Pause/Resume")
        print("  Left/Right: Previous/Next image")
        print("  R: Restart from beginning")
        print("  F: Toggle fullscreen")
        print("  Esc or Q: Quit")
        
        # Start slideshow
        slideshow.start_slideshow()
        
        return 0
        
    except KeyboardInterrupt:
        print("\nSlideshow interrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())