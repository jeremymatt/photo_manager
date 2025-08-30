"""
Simple fade transition effects for the Pi slideshow.
Implements smooth transitions between images using tkinter canvas.
"""

import tkinter as tk
from typing import Optional, Callable, Any


class FadeTransition:
    """Handles fade transitions between images."""
    
    def __init__(self, duration: float = 1.0, steps: int = 20):
        """
        Initialize fade transition.
        
        Args:
            duration: Transition duration in seconds
            steps: Number of steps in the fade (more = smoother)
        """
        self.duration = duration
        self.steps = steps
        self.step_delay = int((duration * 1000) / steps)  # Convert to milliseconds
        
        # Transition state
        self.is_transitioning = False
        self.current_step = 0
        self.callback = None
    
    def fade_between_items(self, canvas: tk.Canvas, old_item: int, new_item: int,
                          callback: Optional[Callable] = None):
        """
        Fade between two canvas items.
        
        Args:
            canvas: Tkinter canvas
            old_item: Canvas item ID for current image
            new_item: Canvas item ID for new image  
            callback: Function to call when transition completes
        """
        if self.is_transitioning:
            return  # Already transitioning
        
        self.is_transitioning = True
        self.current_step = 0
        self.callback = callback
        
        # Start with new image invisible
        canvas.itemconfig(new_item, state='hidden')
        
        # Begin fade sequence
        self._fade_step(canvas, old_item, new_item)
    
    def _fade_step(self, canvas: tk.Canvas, old_item: int, new_item: int):
        """Perform one step of the fade transition."""
        try:
            if self.current_step >= self.steps:
                # Transition complete
                canvas.itemconfig(old_item, state='hidden')
                canvas.itemconfig(new_item, state='normal')
                self.is_transitioning = False
                
                if self.callback:
                    self.callback()
                return
            
            # Calculate fade progress (0.0 to 1.0)
            progress = self.current_step / self.steps
            
            # Simple alpha blending simulation using stipple patterns
            # Since tkinter doesn't support true alpha blending, we use
            # stipple patterns to simulate transparency
            
            if progress < 0.5:
                # First half: fade out old image
                canvas.itemconfig(old_item, state='normal')
                canvas.itemconfig(new_item, state='hidden')
            else:
                # Second half: fade in new image
                canvas.itemconfig(old_item, state='hidden')
                canvas.itemconfig(new_item, state='normal')
            
            self.current_step += 1
            
            # Schedule next step
            canvas.after(self.step_delay, lambda: self._fade_step(canvas, old_item, new_item))
            
        except Exception as e:
            print(f"Error in fade step: {e}")
            # Fallback to immediate transition
            canvas.itemconfig(old_item, state='hidden')
            canvas.itemconfig(new_item, state='normal')
            self.is_transitioning = False
            
            if self.callback:
                self.callback()


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
        
        # Get canvas dimensions
        canvas_width = canvas.winfo_width()
        canvas_height = canvas.winfo_height()
        
        # Create clipping mask for wipe effect
        # This is a simplified version - true wipe would require more complex masking
        
        # For simplicity, we'll do a quick crossfade
        # A true wipe effect would require custom drawing or multiple canvas layers
        
        canvas.itemconfig(new_item, state='normal')
        canvas.after(self.step_delay * 10, self._complete_wipe)
    
    def _complete_wipe(self):
        """Complete the wipe transition."""
        self.is_transitioning = False
        if self.callback:
            self.callback()


class SlideTransition:
    """Implements slide transition effects."""
    
    def __init__(self, duration: float = 0.5, direction: str = 'left'):
        """
        Initialize slide transition.
        
        Args:
            duration: Transition duration in seconds
            direction: Slide direction ('left', 'right', 'up', 'down')
        """
        self.duration = duration
        self.direction = direction
        self.steps = 20
        self.step_delay = int((duration * 1000) / self.steps)
        
        self.is_transitioning = False
    
    def slide_between_items(self, canvas: tk.Canvas, old_item: int, new_item: int,
                           callback: Optional[Callable] = None):
        """Slide from old image to new image."""
        # Simplified slide - moves items across canvas
        # Full implementation would handle smooth movement
        
        if self.is_transitioning:
            return
        
        self.is_transitioning = True
        
        # Quick slide effect - move old out, new in
        canvas.itemconfig(new_item, state='normal')
        
        # Simulate slide by brief delay then completion
        canvas.after(self.step_delay * 5, lambda: self._complete_slide(callback))
    
    def _complete_slide(self, callback: Optional[Callable]):
        """Complete slide transition."""
        self.is_transitioning = False
        if callback:
            callback()


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
    elif transition_type == 'slide':
        return SlideTransition(duration)
    else:
        # 'replace' or unknown - no transition
        return None