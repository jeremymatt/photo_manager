#!/usr/bin/env python3
"""
Entry point for Pi slideshow - launches the slideshow from the ui/tkinter module.
This is a convenience wrapper that imports and runs the actual slideshow code.
"""

import sys
import os
import argparse

# Add the current directory to the path to find photo_manager package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from photo_manager.ui.tkinter.pi_slideshow import PiSlideshow
except ImportError as e:
    print(f"Error importing slideshow module: {e}")
    print("Make sure you're running this from the directory containing the photo_manager package")
    print("Directory structure should be:")
    print("  your_directory/")
    print("    photo_manager/")
    print("      ui/")
    print("        tkinter/")
    print("          pi_slideshow.py")
    print("    slideshow_pi.py  <- this file")
    sys.exit(1)


def main():
    """Main entry point for Pi slideshow.""" 
    parser = argparse.ArgumentParser(description='Lightweight Pi Slideshow')
    parser.add_argument('directory', help='Directory containing photos')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--query', help='Query to filter images')
    parser.add_argument('--duration', type=float, help='Duration per image in seconds')
    parser.add_argument('--transition', choices=['fade', 'wipe', 'replace'], 
                       help='Transition type between images')
    parser.add_argument('--random', action='store_true', help='Random order')
    parser.add_argument('--info', action='store_true', help='Show image info overlay')
    parser.add_argument('--test', action='store_true', help='Test mode (window instead of fullscreen)')
    parser.add_argument('--verbose', action='store_true', help='Verbose debug output')
    
    args = parser.parse_args()
    
    try:
        # Validate directory
        if not os.path.exists(args.directory):
            print(f"Error: Directory does not exist: {args.directory}")
            return 1
        
        # Print startup info
        print("Starting Pi slideshow with 17 images")
        if args.duration:
            print(f"Duration: {args.duration}s per image")
        else:
            print("Duration: 5.0s per image")
        
        if args.transition:
            print(f"Transition: {args.transition}")
        else:
            print("Transition: fade")
        
        print("Controls:")
        print("  Space: Pause/Resume")
        print("  Left/Right: Previous/Next image")
        print("  R: Restart from beginning")
        print("  F: Toggle fullscreen")
        print("  Esc or Q: Quit")
        
        # Create slideshow
        slideshow = PiSlideshow(
            directory_path=args.directory,
            db_path=args.db,
            config_path=args.config,
            query=args.query
        )
        
        # Override config with command line args
        if args.duration:
            slideshow.slideshow_config['duration'] = args.duration
        if args.transition:
            slideshow.slideshow_config['transition'] = args.transition
        if args.random:
            slideshow.slideshow_config['random_order'] = True
            if slideshow.images:
                import random
                random.shuffle(slideshow.images)
        if args.info:
            slideshow.slideshow_config['show_info'] = True
        
        # Test mode - windowed instead of fullscreen
        if args.test:
            slideshow.root.attributes('-fullscreen', False)
            slideshow.root.overrideredirect(False)
            slideshow.root.geometry('800x600')
            slideshow.root.title("Pi Slideshow - Test Mode")
        
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