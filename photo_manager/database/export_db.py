"""
Database export functionality for creating subset databases.
Used for Pi deployments with curated image collections.
"""

import os
import shutil
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from .database_manager import DatabaseManager, create_database
from .models import Image, Tag, ImageTag, Directory


def export_subset_database(source_db_manager: DatabaseManager, 
                          images: List[Image],
                          target_db_path: str,
                          update_file_paths: bool = True,
                          path_mapping: Optional[Dict[str, str]] = None) -> bool:
    """
    Create a subset database containing only specified images.
    
    Args:
        source_db_manager: Source database manager
        images: List of images to include in subset
        target_db_path: Path for new subset database
        update_file_paths: Whether to update file paths in subset
        path_mapping: Optional mapping of old paths to new paths
        
    Returns:
        True if successful
    """
    try:
        # Create new database
        if not create_database(target_db_path):
            return False
        
        # Initialize subset database manager
        subset_config = {
            'type': 'sqlite',
            'path': target_db_path
        }
        subset_db_manager = DatabaseManager(subset_config)
        subset_db_manager.initialize_connection()
        
        with source_db_manager.get_session() as source_session:
            with subset_db_manager.get_session() as subset_session:
                # Copy images
                image_id_mapping = {}
                
                for source_image in images:
                    # Create new image record
                    new_image = Image(
                        file_path=_map_file_path(source_image.file_path, path_mapping),
                        filename=source_image.filename,
                        phash=source_image.phash,
                        dhash=source_image.dhash,
                        file_size=source_image.file_size,
                        width=source_image.width,
                        height=source_image.height,
                        date_taken=source_image.date_taken,
                        date_added=datetime.utcnow(),
                        photographer=source_image.photographer,
                        location_lat=source_image.location_lat,
                        location_lng=source_image.location_lng,
                        location_name=source_image.location_name,
                        tags_reviewed=source_image.tags_reviewed,
                        is_corrupt=source_image.is_corrupt,
                        load_error=source_image.load_error
                    )
                    
                    subset_session.add(new_image)
                    subset_session.flush()
                    
                    # Store mapping for tag relationships
                    image_id_mapping[source_image.id] = new_image.id
                
                # Copy tags
                tag_id_mapping = {}
                
                # Get all unique tags used by the exported images
                used_tags = set()
                for source_image in images:
                    for image_tag in source_image.tags:
                        used_tags.add(image_tag.tag)
                
                # Copy tag definitions
                for source_tag in used_tags:
                    new_tag = Tag(
                        name=source_tag.name,
                        category=source_tag.category
                    )
                    subset_session.add(new_tag)
                    subset_session.flush()
                    
                    tag_id_mapping[source_tag.id] = new_tag.id
                
                # Copy image-tag relationships
                for source_image in images:
                    new_image_id = image_id_mapping[source_image.id]
                    
                    for image_tag in source_image.tags:
                        new_tag_id = tag_id_mapping[image_tag.tag.id]
                        
                        new_image_tag = ImageTag(
                            image_id=new_image_id,
                            tag_id=new_tag_id,
                            date_applied=image_tag.date_applied
                        )
                        subset_session.add(new_image_tag)
                
                # Add directory record
                export_dir = os.path.dirname(target_db_path)
                subset_db_manager.mark_directory_scanned(
                    subset_session,
                    export_dir,
                    template_path=None,
                    image_count=len(images)
                )
                
                subset_session.commit()
        
        print(f"Subset database created with {len(images)} images: {target_db_path}")
        return True
        
    except Exception as e:
        print(f"Error creating subset database: {e}")
        return False


def _map_file_path(original_path: str, path_mapping: Optional[Dict[str, str]]) -> str:
    """Map file path using provided mapping or return original."""
    if not path_mapping:
        return original_path
    
    for old_prefix, new_prefix in path_mapping.items():
        if original_path.startswith(old_prefix):
            return original_path.replace(old_prefix, new_prefix, 1)
    
    return original_path


def merge_databases(primary_db_path: str, secondary_db_path: str, 
                   conflict_resolution: str = 'skip') -> bool:
    """
    Merge two databases, adding images from secondary to primary.
    
    Args:
        primary_db_path: Path to primary database (target)
        secondary_db_path: Path to secondary database (source)
        conflict_resolution: How to handle conflicts ('skip', 'update', 'duplicate')
        
    Returns:
        True if successful
    """
    try:
        # Initialize both database managers
        primary_config = {'type': 'sqlite', 'path': primary_db_path}
        secondary_config = {'type': 'sqlite', 'path': secondary_db_path}
        
        primary_db = DatabaseManager(primary_config)
        secondary_db = DatabaseManager(secondary_config)
        
        primary_db.initialize_connection()
        secondary_db.initialize_connection()
        
        with primary_db.get_session() as primary_session:
            with secondary_db.get_session() as secondary_session:
                
                # Get all images from secondary database
                secondary_images = secondary_session.query(Image).all()
                
                merged_count = 0
                skipped_count = 0
                
                for sec_image in secondary_images:
                    # Check if image already exists in primary
                    existing = primary_session.query(Image).filter_by(
                        file_path=sec_image.file_path
                    ).first()
                    
                    if existing:
                        if conflict_resolution == 'skip':
                            skipped_count += 1
                            continue
                        elif conflict_resolution == 'update':
                            # Update existing record
                            existing.phash = sec_image.phash
                            existing.dhash = sec_image.dhash
                            existing.tags_reviewed = sec_image.tags_reviewed
                            # Copy tags would require more complex logic
                            continue
                    
                    # Add new image (simplified - doesn't copy tags)
                    new_image = Image(
                        file_path=sec_image.file_path,
                        filename=sec_image.filename,
                        phash=sec_image.phash,
                        dhash=sec_image.dhash,
                        file_size=sec_image.file_size,
                        width=sec_image.width,
                        height=sec_image.height,
                        date_taken=sec_image.date_taken,
                        date_added=datetime.utcnow(),
                        photographer=sec_image.photographer,
                        location_lat=sec_image.location_lat,
                        location_lng=sec_image.location_lng,
                        location_name=sec_image.location_name,
                        tags_reviewed=sec_image.tags_reviewed,
                        is_corrupt=sec_image.is_corrupt,
                        load_error=sec_image.load_error
                    )
                    
                    primary_session.add(new_image)
                    merged_count += 1
                
                primary_session.commit()
        
        print(f"Database merge complete: {merged_count} added, {skipped_count} skipped")
        return True
        
    except Exception as e:
        print(f"Error merging databases: {e}")
        return False


def compact_database(db_path: str) -> bool:
    """
    Compact/vacuum SQLite database to reclaim space.
    
    Args:
        db_path: Path to database file
        
    Returns:
        True if successful
    """
    try:
        config = {'type': 'sqlite', 'path': db_path}
        db_manager = DatabaseManager(config)
        db_manager.initialize_connection()
        
        # Execute VACUUM command
        with db_manager.engine.connect() as connection:
            connection.execute("VACUUM")
        
        print(f"Database compacted: {db_path}")
        return True
        
    except Exception as e:
        print(f"Error compacting database: {e}")
        return False