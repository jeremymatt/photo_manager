"""
Navigation controller for the photo manager application.
Handles image navigation, file operations, and undo/redo functionality.
Uses SQLAlchemy models directly for consistency with tkinter app.
"""

import os
import shutil
import time
import random
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from ...database.models import Image as ImageModel


@dataclass
class NavigationState:
    """Represents the current navigation state."""
    current_index: int
    total_images: int
    current_directory: str
    filter_query: Optional[str]
    sort_order: str
    sort_reverse: bool


@dataclass
class UndoAction:
    """Represents an undoable action."""
    action_type: str
    timestamp: float
    data: Dict[str, Any]
    description: str


class NavigationController(QObject):
    """
    Handles image navigation, file operations, and state management.
    Uses SQLAlchemy models directly for consistency with tkinter app.
    """
    
    # Navigation signals
    image_changed = Signal(object)            # ImageModel object
    navigation_state_changed = Signal(object) # NavigationState
    directory_changed = Signal(str)           # new_directory
    
    # File operation signals
    files_marked_for_deletion = Signal(set)   # marked_file_paths
    files_deleted = Signal(list)              # deleted_file_paths
    file_operation_completed = Signal(str, bool) # operation, success
    
    # Tag operation signals
    tags_copied = Signal(list)                # copied_tags
    tags_pasted = Signal(object, list)        # target_image, pasted_tags
    
    # Undo/redo signals
    action_undone = Signal(object)            # UndoAction
    action_redone = Signal(object)            # UndoAction
    undo_stack_changed = Signal(int, int)     # undo_count, redo_count
    
    def __init__(self, db_manager=None, tag_manager=None, parent=None):
        super().__init__(parent)
        
        self.db_manager = db_manager
        self.tag_manager = tag_manager
        
        # Navigation state
        self.current_images: List[ImageModel] = []
        self.current_index = 0
        self.current_directory = ""
        self.filter_query = None
        self.sort_order = "date_taken"
        self.sort_reverse = True  # Newest first
        
        # File operations
        self.marked_for_deletion: Set[str] = set()
        self.copied_tags: List[Dict[str, Any]] = []
        
        # Undo/redo system
        self.undo_stack: List[UndoAction] = []
        self.redo_stack: List[UndoAction] = []
        self.max_undo_size = 100
    
    def load_directory(self, directory_path: str) -> bool:
        """
        Load images from directory using same pattern as tkinter app.
        
        Args:
            directory_path: Path to directory to load
            
        Returns:
            bool: True if successfully loaded
        """
        if not os.path.exists(directory_path):
            print(f"Directory does not exist: {directory_path}")
            return False
        
        try:
            self.current_directory = directory_path
            self.filter_query = None  # Clear any previous filter
            self.current_images = self._load_images()
            
            # Reset navigation state
            self.current_index = 0
            
            print(f"Loaded {len(self.current_images)} images from directory")
            
            # Emit signals
            self.directory_changed.emit(directory_path)
            self._emit_navigation_state()
            
            if self.current_images:
                self._emit_current_image()
            
            return True
            
        except Exception as e:
            print(f"Error loading directory: {e}")
            return False
    
    def _load_images(self) -> List[ImageModel]:
        """Load images from database based on query (same pattern as tkinter app)."""
        if not self.db_manager:
            print("No database manager available - attempting fallback directory scan")
            return self._fallback_load_images()
        
        try:
            with self.db_manager.get_session() as session:
                if self.filter_query and self.tag_manager:
                    # Use tag manager for filtered queries
                    print(f"Loading images with filter: {self.filter_query}")
                    images = self.tag_manager.get_images_by_query(session, self.filter_query)
                else:
                    # Get all non-corrupt images (same as pi_slideshow.py)
                    print("Loading all non-corrupt images from database")
                    images = session.query(ImageModel).filter(
                        ImageModel.is_corrupt == False
                    ).order_by(ImageModel.date_taken.desc()).all()
                
                print(f"Database query returned {len(images)} images")
                
                # Filter out images that don't actually exist on disk
                valid_images = []
                for img in images:
                    if os.path.exists(img.file_path):
                        valid_images.append(img)
                    else:
                        print(f"Image file not found, skipping: {img.file_path}")
                
                print(f"Found {len(valid_images)} valid images (files exist on disk)")
                return valid_images
                
        except Exception as e:
            print(f"Error loading images from database: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to directory scanning
            return self._fallback_load_images()
    
    def _fallback_load_images(self) -> List[ImageModel]:
        """Fallback: Load images directly from directory if database fails."""
        print("Falling back to directory scanning...")
        images = []
        
        if not self.current_directory:
            print("No current directory for fallback scan")
            return []
        
        try:
            supported_formats = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}
            
            for root, dirs, files in os.walk(self.current_directory):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in supported_formats):
                        file_path = os.path.join(root, file)
                        # Create simple ImageModel-like object
                        img_obj = type('ImageModel', (), {
                            'id': None,
                            'file_path': file_path,
                            'filename': file,
                            'width': None,
                            'height': None,
                            'file_size': None,
                            'date_taken': None,
                            'photographer': None,
                            'is_corrupt': False
                        })()
                        images.append(img_obj)
            
            # Sort by filename if no date info
            images.sort(key=lambda x: x.filename)
            
            print(f"Found {len(images)} images in directory scan")
            return images
            
        except Exception as e:
            print(f"Error scanning directory: {e}")
            return []
    
    def navigate_to_index(self, index: int) -> bool:
        """Navigate to specific image index."""
        if not self._is_valid_index(index):
            return False
        
        self.current_index = index
        self._emit_current_image()
        self._emit_navigation_state()
        return True
    
    def next_image(self) -> bool:
        """Navigate to next image (wrap)."""
        if not self.current_images:
            return False
        self.current_index = (self.current_index + 1) % len(self.current_images)
        self._emit_current_image()
        self._emit_navigation_state()
        return True

    def previous_image(self) -> bool:
        """Navigate to previous image (wrap)."""
        if not self.current_images:
            return False
        self.current_index = (self.current_index - 1) % len(self.current_images)
        self._emit_current_image()
        self._emit_navigation_state()
        return True
    
    def first_image(self) -> bool:
        """Navigate to first image."""
        if not self.current_images:
            return False
        
        self.current_index = 0
        self._emit_current_image()
        self._emit_navigation_state()
        return True
    
    def last_image(self) -> bool:
        """Navigate to last image."""
        if not self.current_images:
            return False
        
        self.current_index = len(self.current_images) - 1
        self._emit_current_image()
        self._emit_navigation_state()
        return True
    
    def apply_filter(self, query: str) -> bool:
        """Apply filter query to current images."""
        try:
            self.filter_query = query
            self.current_images = self._load_images()
            self.current_index = 0
            
            self._emit_navigation_state()
            if self.current_images:
                self._emit_current_image()
            
            return True
            
        except Exception as e:
            print(f"Error applying filter: {e}")
            return False
    
    def clear_filter(self):
        """Clear current filter and reload all images."""
        self.filter_query = None
        self.current_images = self._load_images()
        self.current_index = 0
        self._emit_navigation_state()
        if self.current_images:
            self._emit_current_image()
    
    # File operations
    def mark_for_deletion(self, image_path: Optional[str] = None) -> bool:
        """Mark image for deletion (toggle)."""
        if image_path is None and self.current_images:
            image_path = self.current_images[self.current_index].file_path
        
        if not image_path:
            return False
        
        if image_path in self.marked_for_deletion:
            self.marked_for_deletion.remove(image_path)
            action_desc = f"Unmarked for deletion: {os.path.basename(image_path)}"
        else:
            self.marked_for_deletion.add(image_path)
            action_desc = f"Marked for deletion: {os.path.basename(image_path)}"
        
        # Add to undo stack
        self._add_undo_action("mark_deletion", {'path': image_path}, action_desc)
        
        # Emit signal
        self.files_marked_for_deletion.emit(self.marked_for_deletion.copy())
        return True
    
    def delete_marked_files(self, move_to_trash: bool = True) -> bool:
        """Delete all files marked for deletion."""
        if not self.marked_for_deletion:
            return False
        
        deleted_files = []
        failed_files = []
        
        for file_path in self.marked_for_deletion:
            try:
                if move_to_trash:
                    # Move to .trash subdirectory
                    trash_dir = os.path.join(os.path.dirname(file_path), '.trash')
                    os.makedirs(trash_dir, exist_ok=True)
                    trash_path = os.path.join(trash_dir, os.path.basename(file_path))
                    shutil.move(file_path, trash_path)
                else:
                    os.remove(file_path)
                
                deleted_files.append(file_path)
                
            except Exception as e:
                failed_files.append((file_path, str(e)))
                print(f"Failed to delete {file_path}: {e}")
        
        # Update marked files set
        self.marked_for_deletion = self.marked_for_deletion - set(deleted_files)
        
        # Remove deleted files from current images list
        self.current_images = [
            img for img in self.current_images 
            if img.file_path not in deleted_files
        ]
        
        # Adjust current index if needed
        if self.current_index >= len(self.current_images):
            self.current_index = max(0, len(self.current_images) - 1)
        
        # Emit signals
        self.files_deleted.emit(deleted_files)
        self.files_marked_for_deletion.emit(self.marked_for_deletion.copy())
        
        success = len(failed_files) == 0
        self.file_operation_completed.emit("delete", success)
        
        # Update navigation if images were deleted
        if deleted_files and self.current_images:
            self._emit_current_image()
            self._emit_navigation_state()
        
        return success
    
    def clear_deletion_marks(self):
        """Clear all deletion marks."""
        if self.marked_for_deletion:
            self._add_undo_action(
                "clear_marks",
                {'marked_files': list(self.marked_for_deletion)},
                "Cleared deletion marks"
            )
            
            self.marked_for_deletion.clear()
            self.files_marked_for_deletion.emit(set())
    
    # Tag operations (consistent with tkinter app)
    def copy_tags_from_current(self) -> bool:
        """Copy tags from current image."""
        if not self.current_images or not self.tag_manager:
            return False
        
        try:
            current_image = self.current_images[self.current_index]
            with self.db_manager.get_session() as session:
                # Refresh the image object in this session
                image = session.query(ImageModel).get(current_image.id)
                if not image:
                    print(f"Image with id {current_image.id} not found in database")
                    return False
                    
                tags = self.tag_manager.get_image_tags(session, image)
                
                # Convert to list format for copying
                self.copied_tags = []
                for category, tag_names in tags.items():
                    for tag_name in tag_names:
                        self.copied_tags.append({
                            'category': category,
                            'name': tag_name
                        })
            
            self.tags_copied.emit(self.copied_tags.copy())
            return True
            
        except Exception as e:
            print(f"Error copying tags: {e}")
            return False
    
    def paste_tags_to_current(self) -> bool:
        """Paste copied tags to current image."""
        if not self.current_images or not self.tag_manager or not self.copied_tags:
            return False
        
        try:
            current_image = self.current_images[self.current_index]
            
            with self.db_manager.get_session() as session:
                # Refresh the image object in this session
                image = session.query(ImageModel).get(current_image.id)
                if not image:
                    print(f"Image with id {current_image.id} not found in database")
                    return False
                
                # Apply copied tags
                for tag in self.copied_tags:
                    self.db_manager.add_tag_to_image(
                        session, image, tag['category'], tag['name']
                    )
                
                session.commit()
            
            self.tags_pasted.emit(current_image, self.copied_tags.copy())
            return True
            
        except Exception as e:
            print(f"Error pasting tags: {e}")
            return False
    
    def apply_custom_tag(self, tag_spec: str) -> bool:
        """Apply a custom tag from hotkey specification."""
        if not self.current_images or not self.tag_manager:
            return False
        
        try:
            if '/' not in tag_spec:
                return False
            
            category, tag_name = tag_spec.split('/', 1)
            current_image = self.current_images[self.current_index]
            
            with self.db_manager.get_session() as session:
                # Refresh the image object in this session
                image = session.query(ImageModel).get(current_image.id)
                if not image:
                    print(f"Image with id {current_image.id} not found in database")
                    return False
                
                # Apply tag
                self.db_manager.add_tag_to_image(session, image, category, tag_name)
                session.commit()
            
            return True
            
        except Exception as e:
            print(f"Error applying custom tag: {e}")
            return False
    
    # Undo/redo system (simplified for now)
    def undo_last_action(self) -> bool:
        """Undo the last action."""
        if not self.undo_stack:
            return False
        
        print("Undo functionality not yet implemented")
        return False
    
    def redo_last_action(self) -> bool:
        """Redo the last undone action."""
        if not self.redo_stack:
            return False
        
        print("Redo functionality not yet implemented")
        return False
    
    def _add_undo_action(self, action_type: str, data: Dict[str, Any], description: str):
        """Add an action to the undo stack."""
        action = UndoAction(
            action_type=action_type,
            timestamp=time.time(),
            data=data,
            description=description
        )
        
        self.undo_stack.append(action)
        self.redo_stack.clear()
        
        # Limit undo stack size
        if len(self.undo_stack) > self.max_undo_size:
            self.undo_stack.pop(0)
        
        self._emit_undo_stack_state()
    
    # State management helpers
    def _is_valid_index(self, index: int) -> bool:
        """Check if index is valid for current images."""
        return 0 <= index < len(self.current_images)
    
    def _emit_current_image(self):
        """Emit signal for current image."""
        if self.current_images and self._is_valid_index(self.current_index):
            print(f"Emitting image_changed signal for: {self.current_images[self.current_index].file_path}")
            self.image_changed.emit(self.current_images[self.current_index])
        else:
            print(f"Cannot emit image - no images or invalid index {self.current_index}/{len(self.current_images)}")
    
    def _emit_navigation_state(self):
        """Emit signal for navigation state."""
        state = NavigationState(
            current_index=self.current_index,
            total_images=len(self.current_images),
            current_directory=self.current_directory,
            filter_query=self.filter_query,
            sort_order=self.sort_order,
            sort_reverse=self.sort_reverse
        )
        self.navigation_state_changed.emit(state)
    
    def _emit_undo_stack_state(self):
        """Emit signal for undo/redo stack state."""
        self.undo_stack_changed.emit(len(self.undo_stack), len(self.redo_stack))
    
    # Public getters
    def get_current_image(self) -> Optional[ImageModel]:
        """Get current image object."""
        if self.current_images and self._is_valid_index(self.current_index):
            return self.current_images[self.current_index]
        return None
    
    def get_navigation_state(self) -> NavigationState:
        """Get current navigation state."""
        return NavigationState(
            current_index=self.current_index,
            total_images=len(self.current_images),
            current_directory=self.current_directory,
            filter_query=self.filter_query,
            sort_order=self.sort_order,
            sort_reverse=self.sort_reverse
        )
    
    def get_marked_files(self) -> Set[str]:
        """Get files marked for deletion."""
        return self.marked_for_deletion.copy()
    
    def get_copied_tags(self) -> List[Dict[str, Any]]:
        """Get currently copied tags."""
        return self.copied_tags.copy()
    
    def has_undo_actions(self) -> bool:
        """Check if there are actions to undo."""
        return len(self.undo_stack) > 0
    
    def has_redo_actions(self) -> bool:
        """Check if there are actions to redo."""
        return len(self.redo_stack) > 0