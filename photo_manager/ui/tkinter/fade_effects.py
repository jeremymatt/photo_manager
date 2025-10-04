"""
Fade transition effects for the Pi slideshow using PIL alpha blending.
Implements smooth transitions between images using real image blending.
"""

import tkinter as tk
import os
from typing import Optional, Callable, Any
from PIL import Image, ImageTk


class FadeTransition:
    """Smooth fade transition effect using PIL alpha blending."""
    
    def __init__(self, duration: float = 1.0):
        """
        Initialize fade transition.
        
        Args:
            duration: Transition duration in seconds
        """
        self.duration = duration
        self.fps = 30  # Frames per second for smooth animation
        self.frame_delay = int(1000 / self.fps)  # Milliseconds between frames
        self.total_frames = int(self.duration * self.fps)
        
        self.is_transitioning = False
    
    def fade_between_images(self, canvas, old_image_path, new_image_path, canvas_width, canvas_height, zoom_config, callback=None):
        """Fade between two images using PIL alpha blending."""
        if self.is_transitioning:
            print("Already transitioning, skipping fade")
            if callback:
                callback()
            return
        
        print(f"Starting fade transition: {self.duration}s, {self.total_frames} frames")
        
        try:
            # Load and process both images
            old_pil_img = self._load_and_scale_image(old_image_path, canvas_width, canvas_height, zoom_config)
            new_pil_img = self._load_and_scale_image(new_image_path, canvas_width, canvas_height, zoom_config)
            
            if not old_pil_img or not new_pil_img:
                print("Failed to load one or both images for fade")
                if callback:
                    callback()
                return
            
            # Make both images the same size by padding with black
            max_width = max(old_pil_img.width, new_pil_img.width)
            max_height = max(old_pil_img.height, new_pil_img.height)
            
            old_pil_img = self._pad_image_to_size(old_pil_img, max_width, max_height)
            new_pil_img = self._pad_image_to_size(new_pil_img, max_width, max_height)
            
            self.is_transitioning = True
            
            # Start fade animation
            self._animate_fade_frames(canvas, old_pil_img, new_pil_img, canvas_width, canvas_height, 0, callback)
            
        except Exception as e:
            print(f"Error in fade transition: {e}")
            self.is_transitioning = False
            if callback:
                callback()
    
    def _load_and_scale_image(self, image_path, canvas_width, canvas_height, zoom_config):
        """Load and scale image according to zoom configuration."""
        try:
            if not os.path.exists(image_path):
                print(f"Image not found: {image_path}")
                return None
            
            with Image.open(image_path) as img:
                # Convert to RGB for consistency
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Get zoom settings
                zoom_mode = zoom_config.get('default_zoom', 'fit_to_canvas')
                max_zoom_percent = zoom_config.get('max_zoom_percent', 200)
                max_zoom_factor = max_zoom_percent / 100.0
                
                img_width, img_height = img.size
                
                if zoom_mode == 'fit_to_canvas':
                    # Scale to fit within canvas
                    scale_w = canvas_width / img_width
                    scale_h = canvas_height / img_height
                    scale_factor = min(scale_w, scale_h)
                    
                elif zoom_mode == 'fill_canvas':
                    # Scale to fill canvas
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
                
                # Resize and return copy
                return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
        except Exception as e:
            print(f"Error loading image for fade: {e}")
            return None
    
    def _pad_image_to_size(self, img, target_width, target_height):
        """Pad image with black to reach target dimensions, centered."""
        if img.width == target_width and img.height == target_height:
            return img
        
        # Create new image with black background
        padded = Image.new('RGB', (target_width, target_height), (0, 0, 0))
        
        # Calculate position to center the image
        x = (target_width - img.width) // 2
        y = (target_height - img.height) // 2
        
        # Paste the image onto the black background
        padded.paste(img, (x, y))
        
        return padded
    
    def _animate_fade_frames(self, canvas, old_img, new_img, canvas_width, canvas_height, frame, callback):
        """Animate fade by blending images frame by frame."""
        if frame >= self.total_frames:
            # Animation complete - show final new image
            print(f"Fade animation complete after {frame} frames")
            final_photo = ImageTk.PhotoImage(new_img)
            canvas.delete('fade_image')
            
            fade_item = canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=final_photo, anchor=tk.CENTER,
                tags='fade_image'
            )
            
            # Keep reference to prevent garbage collection
            canvas.fade_photo_ref = final_photo
            
            self.is_transitioning = False
            if callback:
                callback()
            return
        
        try:
            # Calculate fade progress (0.0 to 1.0)
            progress = frame / self.total_frames
            
            if frame % 10 == 0:  # Debug output every 10 frames
                print(f"Fade frame {frame}/{self.total_frames}, progress: {progress:.2f}")
            
            # Create blended image
            blended_img = self._blend_images(old_img, new_img, progress)
            
            if not blended_img:
                print(f"Failed to blend images at frame {frame}")
                self.is_transitioning = False
                if callback:
                    callback()
                return
            
            # Convert to PhotoImage and display
            photo = ImageTk.PhotoImage(blended_img)
            
            # Remove previous fade image
            canvas.delete('fade_image')
            
            # Create new fade image
            fade_item = canvas.create_image(
                canvas_width // 2, canvas_height // 2,
                image=photo, anchor=tk.CENTER,
                tags='fade_image'
            )
            
            # Keep reference to prevent garbage collection
            canvas.fade_photo_ref = photo
            
            # Schedule next frame
            canvas.after(self.frame_delay, lambda: self._animate_fade_frames(
                canvas, old_img, new_img, canvas_width, canvas_height, frame + 1, callback
            ))
            
        except Exception as e:
            print(f"Error in fade animation frame {frame}: {e}")
            self.is_transitioning = False
            if callback:
                callback()
    
    def _blend_images(self, img1, img2, alpha):
        """Blend two PIL images using alpha (0.0 = all img1, 1.0 = all img2)."""
        try:
            # Try numpy approach first (faster)
            import numpy as np
            
            # Convert images to numpy arrays
            arr1 = np.array(img1, dtype=np.float32)
            arr2 = np.array(img2, dtype=np.float32)
            
            # Blend: result = img1 * (1 - alpha) + img2 * alpha
            blended_arr = arr1 * (1.0 - alpha) + arr2 * alpha
            
            # Convert back to uint8 and create PIL image
            blended_arr = np.clip(blended_arr, 0, 255).astype(np.uint8)
            return Image.fromarray(blended_arr)
            
        except ImportError:
            # Fallback without numpy - pixel by pixel blending (slower)
            return self._blend_images_fallback(img1, img2, alpha)
        except Exception as e:
            print(f"Error in numpy blending: {e}")
            return self._blend_images_fallback(img1, img2, alpha)
    
    def _blend_images_fallback(self, img1, img2, alpha):
        """Fallback blending method without numpy."""
        try:
            # Create result image
            result = Image.new('RGB', img1.size)
            
            # Get pixel data
            pixels1 = list(img1.getdata())
            pixels2 = list(img2.getdata())
            
            # Blend each pixel
            blended_pixels = []
            for p1, p2 in zip(pixels1, pixels2):
                r = int(p1[0] * (1.0 - alpha) + p2[0] * alpha)
                g = int(p1[1] * (1.0 - alpha) + p2[1] * alpha)
                b = int(p1[2] * (1.0 - alpha) + p2[2] * alpha)
                blended_pixels.append((r, g, b))
            
            # Set pixel data
            result.putdata(blended_pixels)
            return result
            
        except Exception as e:
            print(f"Error in fallback blending: {e}")
            return None
    
    def fade_between_items(self, canvas, old_item, new_item, callback=None):
        """Legacy method for compatibility with old code."""
        if callback:
            callback()


class WipeTransition:
    """Implements wipe transition effects."""
    
    def __init__(self, duration: float = 1.0, direction: str = 'left_to_right'):
        """
        Initialize wipe transition.
        
        Args:
            duration: Transition duration in seconds
            direction: Wipe direction ('left_to_right', 'right_to_left', 'top_to_bottom', 'bottom_to_top')
        """
        self.duration = duration
        self.direction = direction
        self.steps = 30  # Number of wipe steps
        self.step_delay = int((duration * 1000) / self.steps)
        
        self.is_transitioning = False
    
    def wipe_between_items(self, canvas: tk.Canvas, old_item: int, new_item: int,
                          callback: Optional[Callable] = None):
        """
        Wipe from old image to new image.
        
        Args:
            canvas: Tkinter canvas
            old_item: Canvas item ID for current image
            new_item: Canvas item ID for new image
            callback: Function to call when transition completes
        """
        if self.is_transitioning:
            return
        
        self.is_transitioning = True
        self.callback = callback
        
        # Simple implementation - just show new image after delay
        canvas.itemconfig(new_item, state='normal')
        canvas.after(self.step_delay * 10, self._complete_wipe)
    
    def _complete_wipe(self):
        """Complete the wipe transition."""
        self.is_transitioning = False
        if self.callback:
            self.callback()


def create_transition_effect(transition_type: str, duration: float = 1.0) -> Any:
    """
    Factory function to create transition effects.
    
    Args:
        transition_type: Type of transition ('fade', 'wipe', 'slide', 'replace')
        duration: Transition duration in seconds
        
    Returns:
        Transition effect object
    """
    if transition_type == 'fade':
        return FadeTransition(duration)
    elif transition_type == 'wipe':
        return WipeTransition(duration)
    else:
        # 'replace' or unknown - no transition
        return None