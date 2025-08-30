"""
Duplicate detection using perceptual and difference hashing.
Finds near-duplicate images that may be resized, compressed, or lightly edited.
"""

import os
import threading
import queue
import time
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict

import imagehash
from PIL import Image

from ..database.models import Image as ImageModel


class DuplicateDetector:
    """Handles duplicate image detection using perceptual hashing."""
    
    def __init__(self, config: Dict[str, any]):
        """
        Initialize duplicate detector.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config.get('duplicate_detection', {})
        self.similarity_threshold = self.config.get('similarity_threshold', 5)
        self.algorithms = self.config.get('hash_algorithms', ['phash', 'dhash'])
        self.background_processing = self.config.get('background_processing', True)
        
        # Threading for background hash calculation
        self.hash_queue = queue.Queue()
        self.hash_thread = None
        self.stop_hashing = threading.Event()
        self.hash_callback = None
    
    def start_background_processing(self, callback: Optional[Callable] = None):
        """
        Start background thread for hash calculation.
        
        Args:
            callback: Function to call when hash is calculated (image_path, hashes_dict)
        """
        if not self.background_processing:
            return
            
        self.hash_callback = callback
        
        if not self.hash_thread or not self.hash_thread.is_alive():
            self.stop_hashing.clear()
            self.hash_thread = threading.Thread(target=self._hash_worker, daemon=True)
            self.hash_thread.start()
    
    def stop_background_processing(self):
        """Stop background hash calculation thread."""
        self.stop_hashing.set()
        if self.hash_thread:
            self.hash_thread.join(timeout=2.0)
    
    def queue_image_for_hashing(self, file_path: str):
        """
        Queue an image for background hash calculation.
        
        Args:
            file_path: Path to image file
        """
        if self.background_processing:
            try:
                self.hash_queue.put_nowait(file_path)
            except queue.Full:
                print(f"Hash queue full, skipping {file_path}")
        else:
            # Calculate immediately
            hashes = self.calculate_hashes(file_path)
            if self.hash_callback and hashes:
                self.hash_callback(file_path, hashes)
    
    def _hash_worker(self):
        """Background worker for hash calculation."""
        while not self.stop_hashing.is_set():
            try:
                file_path = self.hash_queue.get(timeout=1.0)
                
                # Calculate hashes
                hashes = self.calculate_hashes(file_path)
                
                # Call callback if provided
                if self.hash_callback and hashes:
                    self.hash_callback(file_path, hashes)
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in hash worker: {e}")
    
    def calculate_hashes(self, file_path: str) -> Optional[Dict[str, str]]:
        """
        Calculate perceptual hashes for an image.
        
        Args:
            file_path: Path to image file
            
        Returns:
            Dictionary with hash algorithm names as keys and hash strings as values
        """
        try:
            if not os.path.exists(file_path):
                return None
                
            with Image.open(file_path) as image:
                # Convert to RGB for consistent hashing
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                
                hashes = {}
                
                if 'phash' in self.algorithms:
                    # Perceptual hash - good for detecting resized/compressed images
                    hashes['phash'] = str(imagehash.phash(image))
                
                if 'dhash' in self.algorithms:
                    # Difference hash - faster, good for exact matches
                    hashes['dhash'] = str(imagehash.dhash(image))
                
                if 'ahash' in self.algorithms:
                    # Average hash - simple but less robust
                    hashes['ahash'] = str(imagehash.average_hash(image))
                
                if 'whash' in self.algorithms:
                    # Wavelet hash - good for different image formats
                    hashes['whash'] = str(imagehash.whash(image))
                
                return hashes
                
        except Exception as e:
            print(f"Error calculating hashes for {file_path}: {e}")
            return None
    
    def find_similar_images(self, target_hashes: Dict[str, str], 
                           all_images: List[ImageModel]) -> List[Tuple[ImageModel, int]]:
        """
        Find images similar to target hashes.
        
        Args:
            target_hashes: Dictionary of hashes to match against
            all_images: List of all images in database
            
        Returns:
            List of (Image, similarity_distance) tuples, sorted by similarity
        """
        similar_images = []
        
        try:
            for image in all_images:
                if image.is_corrupt:
                    continue
                    
                min_distance = float('inf')
                
                # Check distance using available hash algorithms
                if 'phash' in target_hashes and image.phash:
                    distance = self._hamming_distance(target_hashes['phash'], image.phash)
                    min_distance = min(min_distance, distance)
                
                if 'dhash' in target_hashes and image.dhash:
                    distance = self._hamming_distance(target_hashes['dhash'], image.dhash) 
                    min_distance = min(min_distance, distance)
                
                # If similarity is within threshold, add to results
                if min_distance <= self.similarity_threshold:
                    similar_images.append((image, min_distance))
            
            # Sort by similarity (lower distance = more similar)
            similar_images.sort(key=lambda x: x[1])
            return similar_images
            
        except Exception as e:
            print(f"Error finding similar images: {e}")
            return []
    
    def group_duplicates(self, images: List[ImageModel]) -> List[List[ImageModel]]:
        """
        Group images by similarity.
        
        Args:
            images: List of images to group
            
        Returns:
            List of groups, each group is a list of similar images
        """
        try:
            # Group by pHash first (primary algorithm)
            phash_groups = defaultdict(list)
            
            for image in images:
                if image.phash and not image.is_corrupt:
                    phash_groups[image.phash].append(image)
            
            # Find groups with multiple images
            duplicate_groups = []
            for phash, group_images in phash_groups.items():
                if len(group_images) > 1:
                    duplicate_groups.append(group_images)
            
            # TODO: Add cross-hash similarity checking for edge cases
            # where pHash might differ but dHash matches
            
            return duplicate_groups
            
        except Exception as e:
            print(f"Error grouping duplicates: {e}")
            return []
    
    def _hamming_distance(self, hash1: str, hash2: str) -> int:
        """
        Calculate Hamming distance between two hash strings.
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            
        Returns:
            Hamming distance (number of differing bits)
        """
        try:
            if len(hash1) != len(hash2):
                return float('inf')
            
            # Convert hex strings to integers and XOR them
            h1 = int(hash1, 16)
            h2 = int(hash2, 16) 
            
            # Count number of 1s in XOR result (differing bits)
            return bin(h1 ^ h2).count('1')
            
        except Exception:
            return float('inf')
    
    def batch_calculate_hashes(self, file_paths: List[str], 
                              progress_callback: Optional[Callable] = None) -> Dict[str, Dict[str, str]]:
        """
        Calculate hashes for multiple images with progress reporting.
        
        Args:
            file_paths: List of image file paths
            progress_callback: Function to call with progress (current, total)
            
        Returns:
            Dictionary mapping file paths to their hashes
        """
        results = {}
        
        try:
            for i, file_path in enumerate(file_paths):
                if progress_callback:
                    progress_callback(i, len(file_paths))
                
                hashes = self.calculate_hashes(file_path)
                if hashes:
                    results[file_path] = hashes
                    
                # Check if we should stop
                if self.stop_hashing.is_set():
                    break
            
            if progress_callback:
                progress_callback(len(file_paths), len(file_paths))
                
            return results
            
        except Exception as e:
            print(f"Error in batch hash calculation: {e}")
            return results
    
    def cleanup(self):
        """Clean up resources."""
        self.stop_background_processing()


class DuplicateResolver:
    """Handles user interaction for resolving duplicate images."""
    
    def __init__(self):
        self.current_group = []
        self.current_index = 0
        self.resolution_actions = []  # Track user decisions
    
    def set_duplicate_group(self, images: List[ImageModel]):
        """Set the current group of duplicate images."""
        self.current_group = images
        self.current_index = 0
        self.resolution_actions = []
    
    def get_current_image(self) -> Optional[ImageModel]:
        """Get the currently selected image in the group."""
        if 0 <= self.current_index < len(self.current_group):
            return self.current_group[self.current_index]
        return None
    
    def navigate_group(self, delta: int) -> bool:
        """
        Navigate within the current duplicate group.
        
        Args:
            delta: Direction to move (+1 for next, -1 for previous)
            
        Returns:
            True if navigation successful
        """
        if not self.current_group:
            return False
            
        new_index = self.current_index + delta
        if 0 <= new_index < len(self.current_group):
            self.current_index = new_index
            return True
        return False
    
    def mark_to_keep(self, image: ImageModel):
        """Mark an image to be kept during duplicate resolution."""
        self.resolution_actions.append(('keep', image))
    
    def mark_not_duplicate(self, image: ImageModel):
        """Mark an image as not being part of the duplicate group."""
        self.resolution_actions.append(('not_duplicate', image))
    
    def get_images_to_delete(self) -> List[ImageModel]:
        """
        Get list of images that should be deleted based on user actions.
        
        Returns:
            List of images to delete
        """
        kept_images = set()
        not_duplicate_images = set()
        
        for action, image in self.resolution_actions:
            if action == 'keep':
                kept_images.add(image)
            elif action == 'not_duplicate':
                not_duplicate_images.add(image)
        
        # Images to delete = all images in group - kept images - not duplicate images
        to_delete = []
        for image in self.current_group:
            if image not in kept_images and image not in not_duplicate_images:
                to_delete.append(image)
        
        return to_delete
    
    def has_kept_images(self) -> bool:
        """Check if user has marked any images to keep."""
        return any(action == 'keep' for action, _ in self.resolution_actions)


def calculate_image_hashes(file_path: str, algorithms: List[str] = None) -> Optional[Dict[str, str]]:
    """
    Calculate hashes for a single image file.
    
    Args:
        file_path: Path to image file
        algorithms: List of hash algorithms to use
        
    Returns:
        Dictionary mapping algorithm names to hash strings
    """
    if algorithms is None:
        algorithms = ['phash', 'dhash']
    
    try:
        if not os.path.exists(file_path):
            return None
            
        with Image.open(file_path) as image:
            # Convert to RGB for consistent hashing
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            hashes = {}
            
            if 'phash' in algorithms:
                hashes['phash'] = str(imagehash.phash(image))
            
            if 'dhash' in algorithms:
                hashes['dhash'] = str(imagehash.dhash(image))
            
            if 'ahash' in algorithms:
                hashes['ahash'] = str(imagehash.average_hash(image))
            
            if 'whash' in algorithms:
                hashes['whash'] = str(imagehash.whash(image))
            
            return hashes
            
    except Exception as e:
        print(f"Error calculating hashes for {file_path}: {e}")
        return None


def find_duplicates_by_hash(images: List[ImageModel], hash_field: str = 'phash') -> List[List[ImageModel]]:
    """
    Group images by identical hash values.
    
    Args:
        images: List of image models
        hash_field: Database field to group by ('phash' or 'dhash')
        
    Returns:
        List of duplicate groups
    """
    try:
        hash_groups = defaultdict(list)
        
        for image in images:
            if image.is_corrupt:
                continue
                
            hash_value = getattr(image, hash_field, None)
            if hash_value:
                hash_groups[hash_value].append(image)
        
        # Return only groups with multiple images
        return [group for group in hash_groups.values() if len(group) > 1]
        
    except Exception as e:
        print(f"Error grouping by hash: {e}")
        return []


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two hash strings.
    
    Args:
        hash1: First hash string (hex)
        hash2: Second hash string (hex)
        
    Returns:
        Hamming distance (number of differing bits)
    """
    try:
        if len(hash1) != len(hash2):
            return 64  # Max distance for 64-bit hashes
        
        h1 = int(hash1, 16)
        h2 = int(hash2, 16)
        
        return bin(h1 ^ h2).count('1')
        
    except ValueError:
        return 64  # Invalid hash format


def find_similar_by_threshold(target_image: ImageModel, candidates: List[ImageModel], 
                             threshold: int = 5) -> List[Tuple[ImageModel, int]]:
    """
    Find images similar to target within threshold.
    
    Args:
        target_image: Image to find matches for
        candidates: List of candidate images
        threshold: Maximum Hamming distance for similarity
        
    Returns:
        List of (similar_image, distance) tuples
    """
    similar = []
    
    try:
        if not target_image.phash:
            return similar
        
        for candidate in candidates:
            if candidate.id == target_image.id or candidate.is_corrupt:
                continue
                
            if candidate.phash:
                distance = hamming_distance(target_image.phash, candidate.phash)
                if distance <= threshold:
                    similar.append((candidate, distance))
        
        # Sort by similarity
        similar.sort(key=lambda x: x[1])
        return similar
        
    except Exception as e:
        print(f"Error finding similar images: {e}")
        return []