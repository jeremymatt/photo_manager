"""
Qt slideshow mode for the photo manager application.
Provides fullscreen slideshow with transitions and automatic progression.
"""

import os
from typing import Optional, List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QApplication, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QKeyEvent, QPainter


class SlideshowWidget(QWidget):
    """Fullscreen slideshow widget."""
    
    slideshow_ended = Signal()
    
    def __init__(self, images: List[Dict[str, Any]], config: Dict[str, Any]):
        super().__init__()
        
        self.images = images
        self.config = config.get('slideshow', {})
        self.current_index = 0
        self.is_playing = True
        
        # Slideshow settings
        self.duration = self.config.get('duration', 5.0) * 1000  # Convert to ms
        self.random_order = self.config.get('random_order', False)
        self.transition_type = self.config.get('transition', 'fade')
        
        # Setup UI
        self._init_ui()
        
        # Setup timer
        self.timer = QTimer()
        self.timer.timeout.connect(self._next_slide)
        
        # Start slideshow
        if self.images:
            self._display_current_image()
            self._start_timer()
    
    def _init_ui(self):
        """Initialize slideshow UI."""
        self.setWindowTitle("Photo Manager - Slideshow")
        self.setStyleSheet("background-color: black;")
        
        # Make fullscreen
        self.showFullScreen()
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Image display
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label)
        
        # Optional info overlay (hidden by default)
        self.info_label = QLabel()
        self.info_label.setStyleSheet("""
            color: white;
            background-color: rgba(0, 0, 0, 128);
            padding: 10px;
            border-radius: 5px;
        """)
        self.info_label.hide()
        
        # Position info overlay at bottom
        layout.addWidget(self.info_label)
        layout.setStretch(0, 1)  # Image takes most space
    
    def _display_current_image(self):
        """Display current image in slideshow."""
        if not self.images:
            return
        
        try:
            current_image = self.images[self.current_index]
            image_path = current_image['file_path']
            
            if not os.path.exists(image_path):
                self._next_slide()  # Skip missing files
                return
            
            # Load and scale image
            pixmap = QPixmap(image_path)
            if pixmap.isNull():
                self._next_slide()  # Skip invalid images
                return
            
            # Scale to fit screen while maintaining aspect ratio
            screen_size = self.size()
            scaled_pixmap = pixmap.scaled(
                screen_size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            
            # Apply transition effect if enabled
            if self.transition_type == 'fade':
                self._apply_fade_transition(scaled_pixmap)
            else:
                self.image_label.setPixmap(scaled_pixmap)
            
            # Update info overlay (if enabled)
            self._update_info_overlay(current_image)
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            self._next_slide()
    
    def _apply_fade_transition(self, new_pixmap: QPixmap):
        """Apply fade transition between images."""
        # Simple implementation - just set new image
        # TODO: Implement proper fade transition using QPropertyAnimation
        self.image_label.setPixmap(new_pixmap)
    
    def _update_info_overlay(self, image_info: Dict[str, Any]):
        """Update the information overlay."""
        # Show basic info: filename and position
        filename = os.path.basename(image_info['file_path'])
        position = f"{self.current_index + 1}/{len(self.images)}"
        
        info_text = f"{filename}\n{position}"
        
        # Add date if available
        if 'date_taken' in image_info and image_info['date_taken']:
            info_text += f"\n{image_info['date_taken']}"
        
        self.info_label.setText(info_text)
    
    def _next_slide(self):
        """Move to next slide."""
        if not self.images:
            return
        
        if self.random_order:
            import random
            self.current_index = random.randint(0, len(self.images) - 1)
        else:
            self.current_index = (self.current_index + 1) % len(self.images)
        
        self._display_current_image()
    
    def _previous_slide(self):
        """Move to previous slide."""
        if not self.images:
            return
        
        if not self.random_order:
            self.current_index = (self.current_index - 1) % len(self.images)
        
        self._display_current_image()
    
    def _start_timer(self):
        """Start the slideshow timer."""
        if self.is_playing and self.duration > 0:
            self.timer.start(self.duration)
    
    def _stop_timer(self):
        """Stop the slideshow timer."""
        self.timer.stop()
    
    def _toggle_play_pause(self):
        """Toggle slideshow play/pause."""
        self.is_playing = not self.is_playing
        
        if self.is_playing:
            self._start_timer()
        else:
            self._stop_timer()
    
    def _toggle_info_overlay(self):
        """Toggle information overlay visibility."""
        if self.info_label.isVisible():
            self.info_label.hide()
        else:
            self.info_label.show()
    
    def keyPressEvent(self, event: QKeyEvent):
        """Handle keyboard events."""
        key = event.key()
        
        if key == Qt.Key_Escape or key == Qt.Key_Q:
            self._exit_slideshow()
        elif key == Qt.Key_Space:
            self._toggle_play_pause()
        elif key == Qt.Key_Right or key == Qt.Key_Down:
            self._next_slide()
        elif key == Qt.Key_Left or key == Qt.Key_Up:
            self._previous_slide()
        elif key == Qt.Key_I:
            self._toggle_info_overlay()
        elif key == Qt.Key_Home:
            self.current_index = 0
            self._display_current_image()
        elif key == Qt.Key_End:
            self.current_index = len(self.images) - 1
            self._display_current_image()
        else:
            super().keyPressEvent(event)
    
    def _exit_slideshow(self):
        """Exit slideshow mode."""
        self._stop_timer()
        self.slideshow_ended.emit()
        self.close()
    
    def closeEvent(self, event):
        """Handle close event."""
        self._stop_timer()
        self.slideshow_ended.emit()
        event.accept()


def start_slideshow(images: List[Dict[str, Any]], config: Dict[str, Any]) -> SlideshowWidget:
    """
    Start slideshow with given images and configuration.
    
    Args:
        images: List of image dictionaries with file_path and metadata
        config: Configuration dictionary
    
    Returns:
        SlideshowWidget instance
    """
    if not images:
        raise ValueError("No images provided for slideshow")
    
    slideshow = SlideshowWidget(images, config)
    return slideshow