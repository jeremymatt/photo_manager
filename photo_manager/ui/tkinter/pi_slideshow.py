"""
Lightweight slideshow viewer for Raspberry Pi digital picture frames.
Minimal resource usage with database-driven image selection and simple transitions.
"""

import os
import tkinter as tk
import random
import threading
import time
import sys
from typing import List, Optional, Dict, Any
from PIL import Image, ImageTk

try:
    from photo_manager.database.database_manager import DatabaseManager
    from photo_manager.database.models import Image as ImageModel
    from photo_manager.core.tag_manager import TagManager
    from photo_manager.config.config_manager import ConfigManager
    from .fade_effects import FadeTransition
except ImportError:
    # Fallback for development/testing
    print("Warning: Could not import project modules. Using mock classes for testing.")
    
    class DatabaseManager:
        def __init__(self, config): pass
        def initialize_connection(self): return True
        def get_session(self): return MockSession()
    
    class ImageModel:
        def __init__(self, file_path, filename):
            self.file_path = file_path
            self.filename = filename
            self.date_taken = None
            self.photographer = None
            self.is_corrupt = False
    
    class TagManager:
        def __init__(self, db_manager): pass
        def get_images_by_query(self, session, query): return []
    
    class ConfigManager:
        def __init__(self, config_path): pass
        def load_config(self, directory_path):
            return {
                'ui': {
                    'default_zoom': 'fit_to_canvas',
                    'max_zoom_percent': 200
                },
                'slideshow': {
                    'duration': 5.0,
                    'transition': 'replace',
                    'transition_duration': 1.0,
                    'random_order': False,
                    'show_info': False
                },
                'database': {'path': '.photo_manager.db'}
            }
    
    class MockSession:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def query(self, model): return MockQuery()
    
    class MockQuery:
        def filter(self, *args): return self
        def order_by(self, *args): return self
        def all(self): return []
    
    # Import fallback fade transition
    class FadeTransition:
        def __init__(self, duration=1.0): 
            self.duration = duration
        def fade_between_images(self, *args, **kwargs):
            callback = kwargs.get('callback')
            if callback: callback()


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
        
        # Initialize all attributes first
        self.config_manager = None
        self.config = None
        self.slideshow_config = None
        self.db_manager = None
        self.tag_manager = None
        self.images = []
        self.current_index = 0
        self.is_running = False
        self.is_paused = False
        self.current_image_path = None  # Track current image path for fading
        self.root = None
        self.canvas = None
        self.current_image_item = None
        self.next_image_item = None
        self.fade_transition = None
        self.image_cache = {}
        self.preload_thread = None
        self.stop_preload = threading.Event()
        self.screen_width = 800
        self.screen_height = 600
        self.stop_gif_animation = False  # Flag to stop GIF animation
        
        # Initialize components
        self._initialize_config(config_path)
        self._initialize_database(db_path)
        self._initialize_tkinter()
        
        # Load images after everything is set up
        self.images = self._load_images()
        if not self.images:
            # If no database images, fallback to directory scanning
            self.images = self._fallback_load_images()
    
    def _initialize_config(self, config_path: Optional[str]):
        """Initialize configuration."""
        try:
            self.config_manager = ConfigManager(config_path)
            self.config = self.config_manager.load_config(self.directory_path)
            self.slideshow_config = self.config['slideshow']
        except Exception as e:
            print(f"Warning: Could not load config: {e}")
            # Use default config
            self.slideshow_config = {
                'duration': 5.0,
                'transition': 'replace',
                'transition_duration': 1.0,
                'random_order': False,
                'show_info': False
            }
            self.config = {
                'ui': {
                    'default_zoom': 'fit_to_canvas',
                    'max_zoom_percent': 200
                },
                'slideshow': self.slideshow_config,
                'database': {'path': '.photo_manager.db'}
            }
    
    def _initialize_database(self, db_path: Optional[str]):
        """Initialize database connection."""
        try:
            db_config = self.config['database'].copy()
            if not db_path:
                db_path = os.path.join(self.directory_path, db_config['database_name'])
            
            db_config['path'] = db_path
            
            self.db_manager = DatabaseManager(db_config)
            if not self.db_manager.initialize_connection():
                print("Warning: Failed to connect to database, will use directory scanning")
                self.db_manager = None
            else:
                self.tag_manager = TagManager(self.db_manager)
        except Exception as e:
            print(f"Warning: Database initialization failed: {e}")
            self.db_manager = None
    
    def _initialize_tkinter(self):
        """Initialize tkinter window and canvas."""
        try:
            # Create root window
            self.root = tk.Tk()
            self.root.title("Pi Slideshow")
            
            # Force window to appear and update
            self.root.update_idletasks()
            
            # Get actual screen dimensions
            self.screen_width = self.root.winfo_screenwidth()
            self.screen_height = self.root.winfo_screenheight()
            
            print(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
            
            # Configure window
            self.root.configure(bg='black')
            self.root.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
            
            # Set fullscreen
            self.root.attributes('-fullscreen', True)
            self.root.overrideredirect(True)
            
            # Force another update
            self.root.update()
            
            # Create canvas
            self.canvas = tk.Canvas(
                self.root,
                width=self.screen_width,
                height=self.screen_height,
                bg='black',
                highlightthickness=0,
                bd=0
            )
            self.canvas.pack(fill=tk.BOTH, expand=True)
            
            # Final update to ensure canvas is ready
            self.root.update_idletasks()
            
            print("Canvas initialized successfully")
            
            # Bind keyboard controls
            self._bind_keys()
            
            # Force focus to ensure keyboard events work
            self.root.focus_force()
            self.root.grab_set_global()  # Make sure this window gets all events
            
            # Initialize fade transition
            self.fade_transition = FadeTransition(
                self.slideshow_config.get('transition_duration', 1.0)
            )
            
        except Exception as e:
            print(f"Error initializing tkinter: {e}")
            raise
    
    def _bind_keys(self):
        """Bind keyboard controls for slideshow."""
        self.root.bind('<KeyPress-Right>', self.next_image)
        self.root.bind('<KeyPress-Left>', self.previous_image)
        self.root.bind('<KeyPress-space>', self.toggle_pause)
        self.root.bind('<KeyPress-Escape>', self.quit_slideshow)
        self.root.bind('<KeyPress-q>', self.quit_slideshow)
        self.root.bind('<KeyPress-r>', self.restart_slideshow)
        self.root.bind('<KeyPress-f>', self.toggle_fullscreen)
        
        # Also bind the simpler event names for compatibility
        self.root.bind('<Right>', self.next_image)
        self.root.bind('<Left>', self.previous_image)
        self.root.bind('<space>', self.toggle_pause)
        self.root.bind('<Escape>', self.quit_slideshow)
        self.root.bind('<q>', self.quit_slideshow)
        self.root.bind('<r>', self.restart_slideshow)
        self.root.bind('<f>', self.toggle_fullscreen)
        
        # Focus handling - make sure window can receive key events
        self.root.bind('<Button-1>', lambda e: self.root.focus_set())
        self.root.focus_set()
        
        # Make sure the window can receive keyboard focus
        self.root.bind('<FocusIn>', lambda e: print("Window gained focus"))
        self.root.bind('<FocusOut>', lambda e: print("Window lost focus"))
        
        print("Key bindings configured")
    
    def _load_images(self) -> List[ImageModel]:
        """Load images from database based on query."""
        if not self.db_manager:
            return []
        
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
            print(f"Error loading images from database: {e}")
            return []
    
    def _fallback_load_images(self) -> List[ImageModel]:
        """Fallback: Load images directly from directory if database fails."""
        print("Falling back to directory scanning...")
        images = []
        
        try:
            supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}
            
            for root, dirs, files in os.walk(self.directory_path):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in supported_formats):
                        file_path = os.path.join(root, file)
                        # Create simple ImageModel-like object
                        img_obj = ImageModel(file_path, file)
                        images.append(img_obj)
            
            if self.slideshow_config.get('random_order', False):
                random.shuffle(images)
            
            print(f"Found {len(images)} images in directory")
            return images
            
        except Exception as e:
            print(f"Error scanning directory: {e}")
            return []
    
    def start_slideshow(self):
        """Start the slideshow."""
        print("=== Starting slideshow ===")
        
        if not self.images:
            self.show_error("No images to display")
            return
        
        if not self.canvas:
            print("Error: Canvas not initialized")
            return
        
        print(f"Starting slideshow with {len(self.images)} images")
        print(f"Slideshow config: {self.slideshow_config}")
        
        self.is_running = True
        self.is_paused = False
        
        # Start preloading thread
        self._start_preloading()
        
        # Load first image
        print("Loading first image...")
        self.load_current_image()
        
        # Start slideshow timer - THIS IS CRITICAL
        print("Starting slideshow timer...")
        self._schedule_next_image()
        
        print("Starting tkinter main loop...")
        # Start tkinter main loop
        try:
            self.root.mainloop()
        finally:
            self.cleanup()
    
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
                    
                    cache_key = f"{next_image.file_path}_{self.screen_width}x{self.screen_height}"
                    if cache_key not in self.image_cache:
                        self._load_image_to_cache(next_image.file_path)
                
                # Sleep before next preload cycle
                time.sleep(2)
                
            except Exception as e:
                print(f"Error in preload worker: {e}")
                time.sleep(1)
    
    def _load_image_to_cache(self, file_path: str):
        """Load image to cache."""
        try:
            if not os.path.exists(file_path):
                print(f"Image file not found: {file_path}")
                return
            
            cache_key = f"{file_path}_{self.screen_width}x{self.screen_height}"
            
            with Image.open(file_path) as img:
                processed_img = self._process_static_image(
                    img, self.screen_width, self.screen_height, self.config.get('ui', {})
                )
                
                # Cache the processed image
                self.image_cache[cache_key] = ImageTk.PhotoImage(processed_img)
                print(f"Cached image: {os.path.basename(file_path)}")
                
        except Exception as e:
            print(f"Error loading image {file_path}: {e}")
    
    def _process_static_image(self, img, canvas_width, canvas_height, zoom_config):
        """Process a static image (single frame) with zoom settings."""
        # Convert to RGB for consistency
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Get zoom mode and max zoom from config
        zoom_mode = zoom_config.get('default_zoom', 'fit_to_canvas')
        max_zoom_percent = zoom_config.get('max_zoom_percent', 200)
        max_zoom_factor = max_zoom_percent / 100.0
        
        img_width, img_height = img.size
        
        if zoom_mode == 'fit_to_canvas':
            # Calculate scale factors for width and height
            scale_w = canvas_width / img_width
            scale_h = canvas_height / img_height
            
            # Use the smaller scale factor to ensure entire image fits
            scale_factor = min(scale_w, scale_h)
            
        elif zoom_mode == 'fill_canvas':
            # Use larger scale factor to fill canvas (may crop image)
            scale_w = canvas_width / img_width
            scale_h = canvas_height / img_height
            scale_factor = max(scale_w, scale_h)
            
        else:  # no_zoom
            scale_factor = 1.0
        
        # Apply max zoom limit
        scale_factor = min(scale_factor, max_zoom_factor)
        
        # Calculate new dimensions
        new_width = int(img_width * scale_factor)
        new_height = int(img_height * scale_factor)
        
        # Resize and return
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def load_current_image(self, manual_navigation=False):
        """Load and display the current image."""
        if not self.images:
            self.show_error("No images available")
            return
            
        if not self.canvas:
            print("Error: Canvas not available")
            self.show_error("Display error: Canvas not initialized")
            return
        
        current_image = self.images[self.current_index]
        new_image_path = current_image.file_path
        
        print(f"Loading image: {os.path.basename(new_image_path)} (manual: {manual_navigation})")
        
        try:
            # Get canvas dimensions
            self.root.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = self.screen_width
                canvas_height = self.screen_height
            
            # Get zoom configuration
            zoom_config = self.config.get('ui', {})
            
            # Check if the new image is a GIF - GIFs never use fade transitions
            is_new_gif = new_image_path.lower().endswith('.gif')
            is_old_gif = self.current_image_path and self.current_image_path.lower().endswith('.gif')
            
            # Check if we should use fade transition
            transition_type = self.slideshow_config.get('transition', 'replace')
            
            print(f"Transition decision: manual={manual_navigation}, new_is_gif={is_new_gif}, old_is_gif={is_old_gif}, type={transition_type}")
            
            # Skip fade for manual navigation, GIFs, or if no previous image
            if (not manual_navigation and 
                not is_new_gif and  # Never fade TO GIFs
                not is_old_gif and  # Never fade FROM GIFs
                transition_type == 'fade' and 
                self.current_image_path and 
                self.current_image_path != new_image_path and 
                os.path.exists(self.current_image_path)):
                
                # Use fade transition between static images only
                print(f"Using fade transition from {os.path.basename(self.current_image_path)} to {os.path.basename(new_image_path)}")
                
                self.fade_transition.fade_between_images(
                    self.canvas,
                    self.current_image_path,  # old image
                    new_image_path,           # new image
                    canvas_width,
                    canvas_height,
                    zoom_config,
                    callback=lambda: self._fade_complete(new_image_path)
                )
            else:
                # No fade - load image directly
                if manual_navigation:
                    print("Loading image without fade (manual navigation)")
                elif is_new_gif:
                    print("Loading image without fade (new image is GIF)")
                elif is_old_gif:
                    print("Loading image without fade (previous image was GIF)")
                else:
                    print("Loading image without fade (other reason)")
                    
                self._load_image_direct(new_image_path, canvas_width, canvas_height, zoom_config)
                self.current_image_path = new_image_path
            
            # Show image info if configured
            if self.slideshow_config.get('show_info', False):
                self._show_image_info(current_image)
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.show_error(f"Error: {current_image.filename}")
    
    def _load_image_direct(self, image_path, canvas_width, canvas_height, zoom_config):
        """Load image directly without fade transition."""
        try:
            print(f"Loading image directly: {os.path.basename(image_path)}")
            
            # Check if it's an animated GIF
            if image_path.lower().endswith('.gif'):
                self._load_animated_gif(image_path, canvas_width, canvas_height, zoom_config)
                return
            
            # Handle static images
            cache_key = f"{image_path}_{canvas_width}x{canvas_height}"
            if cache_key in self.image_cache:
                photo_image = self.image_cache[cache_key]
                print("Using cached image")
            else:
                # Load and cache the image
                self._load_image_to_cache_with_config(image_path, canvas_width, canvas_height, zoom_config)
                photo_image = self.image_cache.get(cache_key)
            
            if photo_image:
                self._replace_image(photo_image)
            else:
                self.show_error(f"Could not load: {os.path.basename(image_path)}")
                
        except Exception as e:
            print(f"Error in _load_image_direct: {e}")
            self.show_error(f"Error loading: {os.path.basename(image_path)}")
    
    def _load_animated_gif(self, gif_path, canvas_width, canvas_height, zoom_config):
        """Load and display animated GIF with proper scaling."""
        try:
            print(f"Loading GIF file: {os.path.basename(gif_path)}")
            
            # Test if file can be opened
            img = Image.open(gif_path)
            print(f"GIF opened successfully. Mode: {img.mode}, Size: {img.size}")
            
            # Check if it's actually animated
            is_animated = getattr(img, 'is_animated', False)
            n_frames = getattr(img, 'n_frames', 1)
            
            print(f"GIF is_animated: {is_animated}, n_frames: {n_frames}")
            
            if not is_animated or n_frames <= 1:
                print("GIF is not animated or has only 1 frame, treating as static image")
                # Treat as static image
                processed_img = self._process_static_image(img, canvas_width, canvas_height, zoom_config)
                photo_image = ImageTk.PhotoImage(processed_img)
                self._replace_image(photo_image)
                img.close()
                return
            
            # Stop any existing GIF animation
            self._stop_gif_animation()
            
            # Start GIF animation
            self._animate_gif(gif_path, canvas_width, canvas_height, zoom_config)
            img.close()
                
        except Exception as e:
            print(f"Error loading animated GIF: {e}")
            import traceback
            traceback.print_exc()
            self.show_error(f"Error loading GIF: {os.path.basename(gif_path)}")
    
    def _stop_gif_animation(self):
        """Stop any running GIF animation."""
        print("Stopping GIF animation")
        self.stop_gif_animation = True
        
        # Also clear any remaining GIF frames from canvas
        self.canvas.delete('gif_frame')
        
        # Cancel any pending GIF animation callbacks
        if hasattr(self, 'gif_animation_id'):
            self.root.after_cancel(self.gif_animation_id)
            delattr(self, 'gif_animation_id')
        
    def _animate_gif(self, gif_path, canvas_width, canvas_height, zoom_config):
        """Animate GIF frames."""
        try:
            print(f"Starting GIF animation for: {os.path.basename(gif_path)}")
            
            # Stop any existing animation first
            self._stop_gif_animation()
            
            # Clear ALL existing images and frames
            self.canvas.delete('current_image')
            self.canvas.delete('fade_image')
            self.canvas.delete('gif_frame')
            
            self.stop_gif_animation = False  # Reset flag
            
            # Load GIF and extract frames
            img = Image.open(gif_path)
            frames = []
            durations = []
            
            # Get GIF speed multiplier from config
            gif_speed = self.slideshow_config.get('gif_animation_speed', 1.0)
            print(f"GIF animation speed multiplier: {gif_speed}")
            
            # Extract all frames
            print(f"Processing {img.n_frames} GIF frames...")
            try:
                for frame_num in range(img.n_frames):
                    if frame_num < 3:  # Only print first few frames
                        print(f"Processing frame {frame_num}")
                    img.seek(frame_num)
                    
                    # Make a copy of the frame
                    frame = img.copy()
                    
                    # Convert to RGB if needed
                    if frame.mode != 'RGB':
                        frame = frame.convert('RGB')
                    
                    # Process frame with zoom settings
                    processed_frame = self._process_static_image(frame, canvas_width, canvas_height, zoom_config)
                    frames.append(ImageTk.PhotoImage(processed_frame))
                    
                    # Get frame duration (default 100ms if not specified)
                    duration = img.info.get('duration', 100)
                    # Apply speed multiplier (lower duration = faster animation)
                    adjusted_duration = max(int(duration / gif_speed), 50)  # Minimum 50ms per frame
                    durations.append(adjusted_duration)
                    
                    if frame_num < 3:  # Only print first few frames
                        print(f"Frame {frame_num}: duration={duration}ms -> {adjusted_duration}ms")
                
            except Exception as e:
                print(f"Error processing GIF frames: {e}")
                img.close()
                return
            
            img.close()
            
            if not frames:
                print("No frames extracted from GIF")
                return
                
            print(f"Successfully extracted {len(frames)} frames from GIF")
            
            # Make sure we're starting fresh
            if hasattr(self, 'gif_animation_id'):
                self.root.after_cancel(self.gif_animation_id)
            
            # Start animation loop
            self._gif_animation_loop(frames, durations, canvas_width, canvas_height, 0)
                
        except Exception as e:
            print(f"Error animating GIF: {e}")
            import traceback
            traceback.print_exc()
            self.show_error(f"GIF animation error: {os.path.basename(gif_path)}")
    
    def _gif_animation_loop(self, frames, durations, canvas_width, canvas_height, frame_index):
        """Loop through GIF frames."""
        if not self.is_running or not frames or getattr(self, 'stop_gif_animation', False):
            print(f"Stopping GIF animation loop. Running: {self.is_running}, Frames: {len(frames) if frames else 0}, Stop flag: {getattr(self, 'stop_gif_animation', False)}")
            # Clear any GIF frames when stopping
            self.canvas.delete('gif_frame')
            if hasattr(self, 'gif_animation_id'):
                delattr(self, 'gif_animation_id')
            return
        
        try:
            # Show current frame
            self.canvas.delete('gif_frame')
            
            frame_item = self.canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=frames[frame_index],
                anchor=tk.CENTER,
                tags='gif_frame'
            )
            
            # Keep reference to prevent garbage collection
            self.canvas.gif_frame_ref = frames[frame_index]
            
            # Calculate next frame
            next_frame = (frame_index + 1) % len(frames)
            frame_duration = durations[frame_index]
            
            # Debug output for first few frames and every 10th frame
            if frame_index < 5 or frame_index % 10 == 0:
                print(f"GIF frame {frame_index}/{len(frames)} - duration: {frame_duration}ms -> next: {next_frame}")
            
            # Schedule next frame and store the callback ID so we can cancel it
            self.gif_animation_id = self.root.after(frame_duration, lambda: self._gif_animation_loop(
                frames, durations, canvas_width, canvas_height, next_frame
            ))
            
        except Exception as e:
            print(f"Error in GIF animation loop at frame {frame_index}: {e}")
            import traceback
            traceback.print_exc()
    
    def _load_image_to_cache_with_config(self, file_path, canvas_width, canvas_height, zoom_config):
        """Load image to cache with specific canvas dimensions and zoom config."""
        try:
            if not os.path.exists(file_path):
                print(f"Image file not found: {file_path}")
                return
            
            # Create cache key that includes dimensions
            cache_key = f"{file_path}_{canvas_width}x{canvas_height}"
            
            with Image.open(file_path) as img:
                processed_img = self._process_static_image(img, canvas_width, canvas_height, zoom_config)
                
                # Cache the processed image with dimension-specific key
                self.image_cache[cache_key] = ImageTk.PhotoImage(processed_img)
                print(f"Cached image: {os.path.basename(file_path)}")
                
        except Exception as e:
            print(f"Error loading image {file_path}: {e}")
    
    def _fade_complete(self, new_image_path):
        """Called when fade transition completes."""
        print(f"Fade complete to {os.path.basename(new_image_path)}")
        self.current_image_path = new_image_path
        
        # The fade_image tag now contains the final image
        # Remove old current_image items
        self.canvas.delete('current_image')
        
        # Retag fade_image as current_image for consistency
        fade_items = self.canvas.find_withtag('fade_image')
        for item in fade_items:
            self.canvas.itemconfig(item, tags='current_image')
        
        # Update current_image_item reference
        current_items = self.canvas.find_withtag('current_image')
        self.current_image_item = current_items[0] if current_items else None
        
        # Check if the faded-to image is a GIF that needs to be animated
        if new_image_path.lower().endswith('.gif'):
            print(f"Fade completed to GIF - starting animation for {os.path.basename(new_image_path)}")
            
            # Get canvas dimensions
            self.root.update_idletasks()
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width <= 1 or canvas_height <= 1:
                canvas_width = self.screen_width
                canvas_height = self.screen_height
            
            # Get zoom configuration
            zoom_config = self.config.get('ui', {})
            
            # Clear the static fade result and start GIF animation
            self.canvas.delete('current_image')
            self.canvas.delete('fade_image')
            
            # Start GIF animation
            self._load_animated_gif(new_image_path, canvas_width, canvas_height, zoom_config)
    
    def _replace_image(self, photo_image: ImageTk.PhotoImage):
        """Replace current image without transition, centered in canvas."""
        if not self.canvas:
            print("Error: Cannot replace image - canvas not available")
            return
        
        print("Replacing image on canvas")
        
        # Stop any GIF animations first
        self._stop_gif_animation()
        
        # Remove ALL previous images and frames
        self.canvas.delete('current_image')
        self.canvas.delete('fade_image')
        self.canvas.delete('gif_frame')
        
        # Get canvas center
        self.root.update_idletasks()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        
        # Fallback if canvas dimensions not ready
        if canvas_width <= 1 or canvas_height <= 1:
            canvas_width = self.screen_width
            canvas_height = self.screen_height
        
        # Add new image centered in canvas
        self.current_image_item = self.canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=photo_image,
            anchor=tk.CENTER,
            tags='current_image'
        )
        
        self.canvas.update()
    
    def _show_image_info(self, image: ImageModel):
        """Display image information overlay."""
        if not self.canvas:
            return
        
        try:
            # Remove previous info
            self.canvas.delete('info_text')
            
            info_parts = []
            info_parts.append(f"{self.current_index + 1}/{len(self.images)}")
            info_parts.append(image.filename)
            
            if hasattr(image, 'date_taken') and image.date_taken:
                info_parts.append(image.date_taken.strftime("%Y-%m-%d %H:%M"))
            
            if hasattr(image, 'photographer') and image.photographer:
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
        print(f"next_image called (event: {event is not None})")
        
        # Stop any running GIF animation
        self._stop_gif_animation()
        
        if self.images:
            old_index = self.current_index
            self.current_index = (self.current_index + 1) % len(self.images)
            print(f"Moving from image {old_index} to {self.current_index}")
            # Pass manual_navigation=True to skip fade transitions
            self.load_current_image(manual_navigation=True)
    
    def previous_image(self, event=None):
        """Move to previous image."""
        print(f"previous_image called (event: {event is not None})")
        
        # Stop any running GIF animation  
        self._stop_gif_animation()
        
        if self.images:
            old_index = self.current_index
            self.current_index = (self.current_index - 1) % len(self.images)
            print(f"Moving from image {old_index} to {self.current_index}")
            # Pass manual_navigation=True to skip fade transitions
            self.load_current_image(manual_navigation=True)
    
    def toggle_pause(self, event=None):
        """Toggle slideshow pause."""
        self.is_paused = not self.is_paused
        print(f"Slideshow {'paused' if self.is_paused else 'resumed'}")
        
        if not self.is_paused:
            # Resume slideshow
            self._schedule_next_image()
    
    def restart_slideshow(self, event=None):
        """Restart slideshow from beginning."""
        self.current_index = 0
        self.is_paused = False
        self.load_current_image()
        self._schedule_next_image()
        print("Slideshow restarted")
    
    def toggle_fullscreen(self, event=None):
        """Toggle fullscreen mode."""
        try:
            current_state = self.root.attributes('-fullscreen')
            self.root.attributes('-fullscreen', not current_state)
        except Exception as e:
            print(f"Error toggling fullscreen: {e}")
    
    def quit_slideshow(self, event=None):
        """Quit the slideshow application."""
        print("Quitting slideshow...")
        self.is_running = False
        self.stop_preload.set()
        
        if self.preload_thread:
            self.preload_thread.join(timeout=1.0)
        
        if self.root:
            self.root.quit()
            self.root.destroy()
    
    def _schedule_next_image(self):
        """Schedule the next image transition."""
        print(f"_schedule_next_image called - running: {self.is_running}, paused: {self.is_paused}")
        
        if self.is_running and not self.is_paused and self.root:
            duration_ms = int(self.slideshow_config.get('duration', 5.0) * 1000)
            print(f"Scheduling next image in {duration_ms}ms")
            self.root.after(duration_ms, self._auto_advance)
        else:
            print("Not scheduling - slideshow stopped or paused")
    
    def _auto_advance(self):
        """Automatically advance to next image."""
        print(f"_auto_advance called - running: {self.is_running}, paused: {self.is_paused}")
        
        if self.is_running and not self.is_paused:
            print("Auto-advancing to next image (with fade if enabled)...")
            
            # Stop any running GIF animation
            self._stop_gif_animation()
            
            if self.images:
                old_index = self.current_index
                self.current_index = (self.current_index + 1) % len(self.images)
                print(f"Auto-advance: Moving from image {old_index} to {self.current_index}")
                # Pass manual_navigation=False to enable fade transitions
                self.load_current_image(manual_navigation=False)
            
            self._schedule_next_image()
        else:
            print("Auto-advance skipped - slideshow stopped or paused")
    
    def show_error(self, message: str):
        """Display error message."""
        print(f"Error: {message}")
        
        if not self.canvas:
            print("Cannot display error on canvas - canvas not initialized")
            return
            
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
        print("Cleaning up resources...")
        self.stop_preload.set()
        if self.preload_thread:
            self.preload_thread.join(timeout=1.0)
        
        self.image_cache.clear()