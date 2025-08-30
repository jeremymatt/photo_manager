"""
Image processing module with caching, pre-loading, and error handling.
Handles image loading, resizing, transformations, and memory management.
"""

import os
import threading
from typing import Optional, Tuple, Dict, List, Any
from collections import OrderedDict
from PIL import Image, ImageTk, ImageEnhance, ImageOps, ImageFile
from PIL.ExifTags import TAGS
import queue
import time

# Allow loading of truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True


class ImageCache:
    """LRU cache for loaded images with pre-loading and retention."""
    
    def __init__(self, max_size_mb: int = 512, preload_count: int = 3, retain_count: int = 2):
        """
        Initialize image cache.
        
        Args:
            max_size_mb: Maximum cache size in megabytes
            preload_count: Number of images to preload ahead
            retain_count: Number of previous images to retain
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.preload_count = preload_count
        self.retain_count = retain_count
        self.cache = OrderedDict()  # LRU cache
        self.current_size_bytes = 0
        self.lock = threading.RLock()
        
        # Pre-loading infrastructure
        self.preload_queue = queue.Queue()
        self.preload_thread = None
        self.stop_preloading = threading.Event()
        
    def start_preloading(self):
        """Start the background preloading thread."""
        if not self.preload_thread or not self.preload_thread.is_alive():
            self.stop_preloading.clear()
            self.preload_thread = threading.Thread(target=self._preload_worker, daemon=True)
            self.preload_thread.start()
    
    def stop_preloading_thread(self):
        """Stop the background preloading thread."""
        self.stop_preloading.set()
        if self.preload_thread:
            self.preload_thread.join(timeout=1.0)
    
    def get(self, file_path: str) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
        """
        Get image from cache or load from disk.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Tuple of (PIL Image, metadata dict) or None if failed
        """
        with self.lock:
            if file_path in self.cache:
                # Move to end (most recently used)
                image_data = self.cache.pop(file_path)
                self.cache[file_path] = image_data
                return image_data['image'], image_data['metadata']
            
        # Not in cache, load from disk
        return self._load_image(file_path, add_to_cache=True)
    
    def preload_images(self, file_paths: List[str], current_index: int):
        """
        Queue images for preloading.
        
        Args:
            file_paths: List of all image paths
            current_index: Current image index
        """
        # Queue next images for preloading
        for i in range(1, self.preload_count + 1):
            next_index = (current_index + i) % len(file_paths)
            next_path = file_paths[next_index]
            
            with self.lock:
                if next_path not in self.cache:
                    try:
                        self.preload_queue.put_nowait(next_path)
                    except queue.Full:
                        break  # Queue full, skip remaining
    
    def _preload_worker(self):
        """Background worker for preloading images."""
        while not self.stop_preloading.is_set():
            try:
                file_path = self.preload_queue.get(timeout=1.0)
                
                # Check if already cached
                with self.lock:
                    if file_path in self.cache:
                        continue
                
                # Load image in background
                self._load_image(file_path, add_to_cache=True)
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in preload worker: {e}")
    
    def _load_image(self, file_path: str, add_to_cache: bool = True) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
        """
        Load image from disk with error handling.
        
        Args:
            file_path: Path to image file
            add_to_cache: Whether to add to cache
            
        Returns:
            Tuple of (PIL Image, metadata dict) or None if failed
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            # Load image
            image = Image.open(file_path)
            
            # Extract basic metadata
            metadata = {
                'width': image.width,
                'height': image.height,
                'format': image.format,
                'mode': image.mode,
                'file_size': os.path.getsize(file_path),
                'has_animation': getattr(image, 'is_animated', False)
            }
            
            # Convert to RGB if needed (for consistent processing)
            if image.mode in ('RGBA', 'LA', 'P'):
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                image = rgb_image
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            if add_to_cache:
                self._add_to_cache(file_path, image.copy(), metadata)
            
            return image, metadata
            
        except Exception as e:
            print(f"Error loading image {file_path}: {e}")
            # Return error metadata for corrupt image handling
            error_metadata = {
                'width': 0,
                'height': 0,
                'format': None,
                'mode': None,
                'file_size': os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                'has_animation': False,
                'load_error': str(e)
            }
            return None, error_metadata
    
    def _add_to_cache(self, file_path: str, image: Image.Image, metadata: Dict[str, Any]):
        """Add image to cache with size management."""
        with self.lock:
            # Estimate image size in memory (width * height * 3 bytes for RGB)
            estimated_size = image.width * image.height * 3
            
            # Make room in cache if needed
            while (self.current_size_bytes + estimated_size > self.max_size_bytes and 
                   len(self.cache) > self.retain_count):
                # Remove least recently used item
                oldest_path, oldest_data = self.cache.popitem(last=False)
                self.current_size_bytes -= oldest_data['size']
            
            # Add to cache
            cache_data = {
                'image': image,
                'metadata': metadata,
                'size': estimated_size,
                'cached_at': time.time()
            }
            
            self.cache[file_path] = cache_data
            self.current_size_bytes += estimated_size
    
    def clear(self):
        """Clear the entire cache."""
        with self.lock:
            self.cache.clear()
            self.current_size_bytes = 0


class ImageProcessor:
    """Main image processing class with caching and transformations."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize image processor.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        ui_config = config.get('ui', {})
        perf_config = config.get('performance', {})
        
        self.cache = ImageCache(
            max_size_mb=perf_config.get('image_cache_size_mb', 512),
            preload_count=ui_config.get('preload_next_images', 3),
            retain_count=ui_config.get('retain_previous_images', 2)
        )
        
        # Image transformation state
        self.zoom_level = 0
        self.brightness_level = 0
        self.contrast_level = 0
        self.rotation = 0
        
        # Zoom multiplier tables
        self.zoom_multipliers = self._create_multiplier_table()
        self.brightness_multipliers = self._create_multiplier_table()
        self.contrast_multipliers = self._create_multiplier_table()
        
        # Start cache preloading
        self.cache.start_preloading()
    
    def _create_multiplier_table(self, base: float = 1.1, max_steps: int = 15) -> Dict[int, float]:
        """Create multiplier table for zoom/brightness/contrast."""
        multipliers = {0: 1.0}
        
        # Positive steps (increase)
        for n in range(1, max_steps + 1):
            multipliers[n] = round(multipliers[n-1] * base, 5)
        
        # Negative steps (decrease)  
        for n in range(-1, -max_steps - 1, -1):
            multipliers[n] = round(multipliers[n+1] / base, 5)
            
        return multipliers
    
    def load_image(self, file_path: str) -> Optional[Tuple[Image.Image, Dict[str, Any]]]:
        """
        Load image with caching.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Tuple of (PIL Image, metadata) or None if failed
        """
        return self.cache.get(file_path)
    
    def preload_around_index(self, file_paths: List[str], current_index: int):
        """Preload images around the current index."""
        self.cache.preload_images(file_paths, current_index)
    
    def process_image(self, image: Image.Image, canvas_size: Tuple[int, int], 
                     fit_mode: str = 'fit_to_canvas') -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Process image with current transformations.
        
        Args:
            image: PIL Image to process
            canvas_size: (width, height) of display canvas
            fit_mode: 'no_zoom', 'fit_to_canvas', or 'fill_canvas'
            
        Returns:
            Tuple of (processed image, processing info dict)
        """
        try:
            # Start with a copy
            processed = image.copy()
            
            # Apply rotation first
            if self.rotation != 0:
                processed = processed.rotate(self.rotation, expand=True)
            
            # Calculate base scaling ratio
            if fit_mode == 'fit_to_canvas':
                scale_ratio = min(canvas_size[0] / processed.width, canvas_size[1] / processed.height)
                scale_ratio = min(scale_ratio, 2.0)  # Max 200% zoom for small images
            elif fit_mode == 'fill_canvas':
                scale_ratio = max(canvas_size[0] / processed.width, canvas_size[1] / processed.height)
            else:  # no_zoom
                scale_ratio = 1.0
            
            # Apply zoom multiplier
            final_scale = scale_ratio * self.zoom_multipliers[self.zoom_level]
            
            # Resize image
            new_size = (
                int(processed.width * final_scale),
                int(processed.height * final_scale)
            )
            processed = processed.resize(new_size, Image.Resampling.LANCZOS)
            
            # Apply brightness adjustment
            if self.brightness_level != 0:
                enhancer = ImageEnhance.Brightness(processed)
                processed = enhancer.enhance(self.brightness_multipliers[self.brightness_level])
            
            # Apply contrast adjustment
            if self.contrast_level != 0:
                enhancer = ImageEnhance.Contrast(processed)
                processed = enhancer.enhance(self.contrast_multipliers[self.contrast_level])
            
            # Processing info for display
            processing_info = {
                'final_size': new_size,
                'scale_ratio': final_scale,
                'zoom_level': self.zoom_level,
                'brightness_level': self.brightness_level,
                'contrast_level': self.contrast_level,
                'rotation': self.rotation
            }
            
            return processed, processing_info
            
        except Exception as e:
            print(f"Error processing image: {e}")
            return image, {'error': str(e)}
    
    def create_error_image(self, canvas_size: Tuple[int, int], error_message: str) -> Image.Image:
        """
        Create a placeholder image for corrupt/missing files.
        
        Args:
            canvas_size: Size of the canvas
            error_message: Error message to display
            
        Returns:
            PIL Image with error message
        """
        try:
            # Create a dark gray background
            error_img = Image.new('RGB', canvas_size, (64, 64, 64))
            
            # TODO: Add text rendering for error message
            # This would require PIL ImageDraw and font handling
            # For now, return solid color as placeholder
            
            return error_img
            
        except Exception:
            # Fallback: small solid color image
            return Image.new('RGB', (100, 100), (128, 0, 0))
    
    def reset_transformations(self):
        """Reset all image transformations to defaults."""
        self.zoom_level = 0
        self.brightness_level = 0
        self.contrast_level = 0
        self.rotation = 0
    
    def adjust_zoom(self, delta: int) -> bool:
        """
        Adjust zoom level.
        
        Args:
            delta: Change in zoom level (+1, -1, etc.)
            
        Returns:
            True if zoom changed, False if at limit
        """
        new_level = self.zoom_level + delta
        if new_level in self.zoom_multipliers:
            self.zoom_level = new_level
            return True
        return False
    
    def adjust_brightness(self, delta: int) -> bool:
        """Adjust brightness level."""
        new_level = self.brightness_level + delta
        if new_level in self.brightness_multipliers:
            self.brightness_level = new_level
            return True
        return False
    
    def adjust_contrast(self, delta: int) -> bool:
        """Adjust contrast level.""" 
        new_level = self.contrast_level + delta
        if new_level in self.contrast_multipliers:
            self.contrast_level = new_level
            return True
        return False
    
    def rotate(self, degrees: int):
        """
        Rotate image by specified degrees.
        
        Args:
            degrees: Rotation in degrees (90, -90, etc.)
        """
        self.rotation = (self.rotation + degrees) % 360
    
    def get_gif_frames(self, file_path: str) -> Optional[List[Image.Image]]:
        """
        Load all frames from an animated GIF.
        
        Args:
            file_path: Path to GIF file
            
        Returns:
            List of PIL Image frames or None if failed
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            with Image.open(file_path) as gif:
                if not getattr(gif, 'is_animated', False):
                    return [gif.copy()]
                
                frames = []
                for frame_num in range(gif.n_frames):
                    gif.seek(frame_num)
                    # Convert frame to RGB
                    frame = gif.convert('RGB')
                    frames.append(frame.copy())
                
                return frames
                
        except Exception as e:
            print(f"Error loading GIF frames from {file_path}: {e}")
            return None
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_preloading_thread()
        self.cache.clear()


def extract_exif_data(image: Image.Image) -> Dict[str, Any]:
    """
    Extract EXIF data from PIL Image.
    
    Args:
        image: PIL Image object
        
    Returns:
        Dictionary with extracted EXIF data
    """
    exif_data = {}
    
    try:
        if hasattr(image, '_getexif') and image._getexif():
            exif = image._getexif()
            
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                exif_data[tag_name] = value
                
        return exif_data
        
    except Exception as e:
        print(f"Error extracting EXIF data: {e}")
        return {}


def get_image_orientation(exif_data: Dict[str, Any]) -> int:
    """
    Get image orientation from EXIF data.
    
    Args:
        exif_data: EXIF data dictionary
        
    Returns:
        Rotation degrees needed to correct orientation
    """
    orientation = exif_data.get('Orientation', 1)
    
    orientation_rotations = {
        1: 0,    # Normal
        2: 0,    # Mirrored horizontal
        3: 180,  # Rotated 180
        4: 180,  # Mirrored vertical  
        5: 90,   # Mirrored horizontal and rotated 90 CCW
        6: 270,  # Rotated 90 CW
        7: 270,  # Mirrored horizontal and rotated 90 CW
        8: 90    # Rotated 90 CCW
    }
    
    return orientation_rotations.get(orientation, 0)


def resize_for_display(image: Image.Image, max_size: Tuple[int, int], 
                      maintain_aspect: bool = True) -> Image.Image:
    """
    Resize image for display while maintaining quality.
    
    Args:
        image: PIL Image to resize
        max_size: Maximum (width, height)
        maintain_aspect: Whether to maintain aspect ratio
        
    Returns:
        Resized PIL Image
    """
    if maintain_aspect:
        image.thumbnail(max_size, Image.Resampling.LANCZOS)
        return image
    else:
        return image.resize(max_size, Image.Resampling.LANCZOS)


def create_thumbnail(image: Image.Image, size: Tuple[int, int] = (256, 256)) -> Image.Image:
    """
    Create a thumbnail of the image.
    
    Args:
        image: PIL Image
        size: Thumbnail size (width, height)
        
    Returns:
        Thumbnail PIL Image
    """
    thumbnail = image.copy()
    thumbnail.thumbnail(size, Image.Resampling.LANCZOS)
    return thumbnail