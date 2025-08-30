"""
Lightweight slideshow viewer for Raspberry Pi digital picture frames.
Minimal resource usage with database-driven image selection and simple transitions.
"""

import os
import tkinter as tk
import random
import threading
import time
from typing import List, Optional, Dict, Any
from PIL import Image, ImageTk

from ...database.database_manager import DatabaseManager
from ...database.models import Image as ImageModel
from ...core.tag_manager import TagManager
from ...config.config_manager import ConfigManager
from .fade_effects import FadeTransition


class PiSlideshow:
    """Lightweight slideshow for Raspberry Pi."""
    
    def __init__(self, directory_path: str, db_path: Optional[str] = None, 
                 config_path: Optional[str] = None, query: Optional[str] = None):
        """
        Initialize Pi slideshow.
        
        Args:
            directory_path: Path to photo directory
            db_path: Optional path to database file
            config_path: Optional path to config file
            query: Optional query to filter images
        """
        self.directory_path = directory_path
        self.query = query
        
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.load_config(directory_path)
        self.slideshow_config = self.config['slideshow']
        
        # Initialize database
        if not db_path:
            db_path = os.path.join(directory_path, '.photo_manager.db')
        
        db_config = self.config['database'].copy()
        db_config['path'] = db_path
        
        self.db_manager = DatabaseManager(db_config)
        if not self.db_manager.initialize_connection():
            raise Exception("Failed to connect to database")
        
        # Initialize tag manager for queries
        self.tag_manager = TagManager(self.db_manager)
        
        # Load images
        self.images = self._load_images()
        if not self.images:
            raise Exception("No images found matching criteria")
        
        # Slideshow state
        self.current_index = 0
        self.is_running = False
        self.is_paused = False
        
        # Tkinter setup
        self.root = tk.Tk()
        self._setup_window()
        
        # Image display
        self.canvas = None
        self.current_image_item = None
        self.next_image_item = None
        
        # Transition effects
        self.fade_transition = FadeTransition(self.slideshow_config.get('transition_duration', 1.0))
        
        # Preloading
        self.image_cache = {}
        self.preload_thread = None
        self.stop_preload = threading.Event()
    
    def _setup_window(self):
        """Setup the main tkinter window for fullscreen slideshow."""
        # Remove window decorations
        self.root.overrideredirect(True)
        
        # Set fullscreen
        self.root.attributes('-fullscreen', True)
        
        # Get screen dimensions
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        
        # Set black background
        self.root.configure(bg='black')
        
        # Create canvas
        self.canvas = tk.Canvas(
            self.root,
            width=self.screen_width,
            height=self.screen_height,
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack()
        
        # Bind keyboard controls
        self._bind_keys()
        
        # Focus for keyboard input
        self.root.focus_set()
    
    def _bind_keys(self):
        """Bind keyboard controls for slideshow."""
        self.root.bind('<Right>', self.next_image)
        self.root.bind('<Left>', self.previous_image)
        self.root.bind('<space>', self.toggle_pause)
        self.root.bind('<Escape>', self.quit_slideshow)
        self.root.bind('<q>', self.quit_slideshow)
        self.root.bind('<r>', self.restart_slideshow)
        self.root.bind('<f>', self.toggle_fullscreen)
        
        # Focus handling
        self.root.bind('<Button-1>', lambda e: self.root.focus_set())
    
    def _load_images(self) -> List[ImageModel]:
        """Load images from database based on query."""
        try:
            with self.db_manager.get_session() as session:
                if self.query:
                    images = self.tag_manager.get_images_by_query(session, self.query)
                else:
                    # Get all non-corrupt images
                    images = session.query(ImageModel).filter(
                        ImageModel.is_corrupt == False
                    ).order_by(ImageModel.date_taken.desc()).all()
                
                if self.slideshow_config.get('random_order', False):
                    random.shuffle(images)
                
                return images
                
        except Exception as e:
            print(f"Error loading images: {e}")
            return []
    
    def start_slideshow(self):
        """Start the slideshow."""
        if not self.images:
            self.show_error("No images to display")
            return
        
        self.is_running = True
        self.is_paused = False
        
        # Start preloading thread
        self._start_preloading()
        
        # Load first image
        self.load_current_image()
        
        # Start slideshow timer
        self._schedule_next_image()
        
        # Start tkinter main loop
        self.root.mainloop()
    
    def _start_preloading(self):
        """Start background image preloading."""
        self.stop_preload.clear()
        self.preload_thread = threading.Thread(target=self._preload_worker, daemon=True)
        self.preload_thread.start()
    
    def _preload_worker(self):
        """Background worker for preloading images."""
        preload_ahead = 3  # Number of images to preload ahead
        
        while not self.stop_preload.is_set():
            try:
                for i in range(1, preload_ahead + 1):
                    if self.stop_preload.is_set():
                        break
                    
                    next_index = (self.current_index + i) % len(self.images)
                    next_image = self.images[next_index]
                    
                    if next_image.file_path not in self.image_cache:
                        self._load_image_to_cache(next_image.file_path)
                
                # Sleep before next preload cycle
                time.sleep(2)
                
            except Exception as e:
                print(f"Error in preload worker: {e}")
                time.sleep(1)
    
    def _load_image_to_cache(self, file_path: str):
        """Load image into cache."""
        try:
            if not os.path.exists(file_path):
                return
            
            with Image.open(file_path) as img:
                # Convert to RGB for consistency
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to screen size
                img.thumbnail((self.screen_width, self.screen_height), Image.Resampling.LANCZOS)
                
                # Cache the processed image
                self.image_cache[file_path] = ImageTk.PhotoImage(img)
                
        except Exception as e:
            print(f"Error loading image {file_path}: {e}")
    
    def load_current_image(self):
        """Load and display the current image."""
        if not self.images:
            return
        
        current_image = self.images[self.current_index]
        
        try:
            # Check cache first
            if current_image.file_path in self.image_cache:
                photo_image = self.image_cache[current_image.file_path]
            else:
                # Load directly if not cached
                self._load_image_to_cache(current_image.file_path)
                photo_image = self.image_cache.get(current_image.file_path)
            
            if photo_image:
                # Apply transition effect
                transition_type = self.slideshow_config.get('transition', 'replace')
                
                if transition_type == 'fade' and self.current_image_item:
                    self._fade_to_image(photo_image)
                else:
                    self._replace_image(photo_image)
                
                # Show image info if configured
                if self.slideshow_config.get('show_info', False):
                    self._show_image_info(current_image)
            else:
                self.show_error(f"Could not load: {current_image.filename}")
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.show_error(f"Error: {current_image.filename}")
    
    def _replace_image(self, photo_image: ImageTk.PhotoImage):
        """Replace current image without transition."""
        # Remove previous image
        if self.current_image_item:
            self.canvas.delete(self.current_image_item)
        
        # Add new image centered
        self.current_image_item = self.canvas.create_image(
            self.screen_width // 2,
            self.screen_height // 2,
            image=photo_image,
            anchor=tk.CENTER
        )
        
        self.canvas.update()
    
    def _fade_to_image(self, photo_image: ImageTk.PhotoImage):
        """Fade from current image to new image."""
        if not self.current_image_item:
            self._replace_image(photo_image)
            return
        
        # Create new image item (initially hidden)
        new_image_item = self.canvas.create_image(
            self.screen_width // 2,
            self.screen_height // 2,
            image=photo_image,
            anchor=tk.CENTER
        )
        
        # Perform fade transition
        self.fade_transition.fade_between_items(
            self.canvas, 
            self.current_image_item, 
            new_image_item,
            callback=self._fade_complete
        )
        
        self.next_image_item = new_image_item
    
    def _fade_complete(self):
        """Called when fade transition completes."""
        if self.current_image_item:
            self.canvas.delete(self.current_image_item)
        
        self.current_image_item = self.next_image_item
        self.next_image_item = None
    
    def _show_image_info(self, image: ImageModel):
        """Display image information overlay."""
        try:
            # Remove previous info
            self.canvas.delete('info_text')
            
            info_parts = []
            info_parts.append(f"{self.current_index + 1}/{len(self.images)}")
            info_parts.append(image.filename)
            
            if image.date_taken:
                info_parts.append(image.date_taken.strftime("%Y-%m-%d %H:%M"))
            
            if image.photographer:
                info_parts.append(f"by {image.photographer}")
            
            info_text = " | ".join(info_parts)
            
            # Create text with background
            text_item = self.canvas.create_text(
                10, self.screen_height - 30,
                text=info_text,
                fill='white',
                font=('Arial', 12),
                anchor='w',
                tags='info_text'
            )
            
            # Create background rectangle
            bbox = self.canvas.bbox(text_item)
            if bbox:
                bg_item = self.canvas.create_rectangle(
                    bbox[0] - 5, bbox[1] - 2, bbox[2] + 5, bbox[3] + 2,
                    fill='black',
                    outline='',
                    tags='info_text'
                )
                
                # Raise text above background
                self.canvas.tag_raise(text_item, bg_item)
            
        except Exception as e:
            print(f"Error showing image info: {e}")
    
    def next_image(self, event=None):
        """Move to next image."""
        if self.images:
            self.current_index = (self.current_index + 1) % len(self.images)
            self.load_current_image()
    
    def previous_image(self, event=None):
        """Move to previous image.""" 
        if self.images:
            self.current_index = (self.current_index - 1) % len(self.images)
            self.load_current_image()
    
    def toggle_pause(self, event=None):
        """Toggle slideshow pause."""
        self.is_paused = not self.is_paused
        
        if not self.is_paused:
            # Resume slideshow
            self._schedule_next_image()
    
    def restart_slideshow(self, event=None):
        """Restart slideshow from beginning."""
        self.current_index = 0
        self.is_paused = False
        self.load_current_image()
        self._schedule_next_image()
    
    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode."""
        current_state = self.root.attributes('-fullscreen')
        self.root.attributes('-fullscreen', not current_state)
    
    def quit_slideshow(self, event=None):
        """Quit the slideshow application."""
        self.is_running = False
        self.stop_preload.set()
        
        if self.preload_thread:
            self.preload_thread.join(timeout=1.0)
        
        self.root.quit()
        self.root.destroy()
    
    def _schedule_next_image(self):
        """Schedule the next image transition."""
        if self.is_running and not self.is_paused:
            duration_ms = int(self.slideshow_config.get('duration', 5.0) * 1000)
            self.root.after(duration_ms, self._auto_advance)
    
    def _auto_advance(self):
        """Automatically advance to next image."""
        if self.is_running and not self.is_paused:
            self.next_image()
            self._schedule_next_image()
    
    def show_error(self, message: str):
        """Display error message."""
        self.canvas.delete('all')
        
        error_text = self.canvas.create_text(
            self.screen_width // 2,
            self.screen_height // 2,
            text=message,
            fill='red',
            font=('Arial', 24),
            anchor=tk.CENTER
        )
        
        self.canvas.update()
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_preload.set()
        if self.preload_thread:
            self.preload_thread.join(timeout=1.0)
        
        self.image_cache.clear()


def main():
    """Main entry point for Pi slideshow.""" 
    import argparse
    
    parser = argparse.ArgumentParser(description='Lightweight Pi Slideshow')
    parser.add_argument('directory', help='Directory containing photos')
    parser.add_argument('--db', help='Path to database file')
    parser.add_argument('--config', help='Path to config file')
    parser.add_argument('--query', help='Query to filter images')
    parser.add_argument('--duration', type=float, help='Duration per image in seconds')
    parser.add_argument('--random', action='store_true', help='Random order')
    
    args = parser.parse_args()
    
    try:
        # Validate directory
        if not os.path.exists(args.directory):
            print(f"Error: Directory does not exist: {args.directory}")
            return 1
        
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
        if args.random:
            slideshow.slideshow_config['random_order'] = True
            random.shuffle(slideshow.images)
        
        print(f"Starting slideshow with {len(slideshow.images)} images")
        print("Controls: Space=pause, Left/Right=navigate, Esc/Q=quit")
        
        # Start slideshow
        slideshow.start_slideshow()
        
        return 0
        
    except KeyboardInterrupt:
        print("\nSlideshow interrupted")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(main())