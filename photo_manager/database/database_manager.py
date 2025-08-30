"""
Database manager for the photo manager application.
Handles database connections, migrations, and core database operations.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from .models import Base, Image, Tag, ImageTag, Directory, get_or_create_tag, TAG_CATEGORIES


class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, db_config: dict):
        """
        Initialize database manager.
        
        Args:
            db_config: Dictionary with database configuration
                      {'type': 'sqlite', 'path': 'db_path'} or
                      {'type': 'postgresql', 'connection_string': '...'}
        """
        self.db_config = db_config
        self.engine = None
        self.Session = None
        
    def initialize_connection(self):
        """Create database engine and session factory."""
        try:
            if self.db_config['type'] == 'sqlite':
                db_path = self.db_config['path']
                # Ensure directory exists
                os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
                self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
            elif self.db_config['type'] == 'postgresql':
                self.engine = create_engine(self.db_config['connection_string'])
            elif self.db_config['type'] == 'mysql':
                self.engine = create_engine(self.db_config['connection_string'])
            else:
                raise ValueError(f"Unsupported database type: {self.db_config['type']}")
                
            self.Session = sessionmaker(bind=self.engine)
            
            # Create tables if they don't exist
            Base.metadata.create_all(self.engine)
            
            return True
            
        except Exception as e:
            print(f"Error initializing database: {e}")
            return False
    
    def get_session(self) -> Session:
        """Get a new database session."""
        if not self.Session:
            if not self.initialize_connection():
                raise RuntimeError("Failed to initialize database connection")
        return self.Session()
    
    def backup_database(self, backup_path: Optional[str] = None) -> bool:
        """
        Create a backup of the database.
        
        Args:
            backup_path: Optional custom backup path
            
        Returns:
            True if backup successful
        """
        if self.db_config['type'] != 'sqlite':
            print("Backup only supported for SQLite databases")
            return False
            
        try:
            source = self.db_config['path']
            if not backup_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{source}.backup_{timestamp}"
            
            shutil.copy2(source, backup_path)
            print(f"Database backed up to: {backup_path}")
            return True
            
        except Exception as e:
            print(f"Backup failed: {e}")
            return False
    
    def add_image(self, session: Session, file_path: str, **kwargs) -> Optional[Image]:
        """
        Add a new image to the database.
        
        Args:
            session: Database session
            file_path: Absolute path to image file
            **kwargs: Additional image metadata
            
        Returns:
            Image object if successful, None if failed
        """
        try:
            # Check if image already exists
            existing = session.query(Image).filter_by(file_path=file_path).first()
            if existing:
                return existing
                
            # Create new image record
            image = Image(
                file_path=file_path,
                filename=os.path.basename(file_path),
                **kwargs
            )
            
            session.add(image)
            session.flush()  # Get ID without committing
            return image
            
        except Exception as e:
            print(f"Error adding image {file_path}: {e}")
            return None
    
    def add_tag_to_image(self, session: Session, image: Image, category: str, tag_name: str) -> bool:
        """
        Add a tag to an image.
        
        Args:
            session: Database session
            image: Image object
            category: Tag category (must be in TAG_CATEGORIES)
            tag_name: Name of the tag
            
        Returns:
            True if successful
        """
        try:
            if category not in TAG_CATEGORIES:
                print(f"Invalid tag category: {category}")
                return False
                
            # Get or create the tag
            tag = get_or_create_tag(session, category, tag_name)
            
            # Check if image already has this tag
            existing = session.query(ImageTag).filter_by(
                image_id=image.id, 
                tag_id=tag.id
            ).first()
            
            if not existing:
                image_tag = ImageTag(image_id=image.id, tag_id=tag.id)
                session.add(image_tag)
                
            return True
            
        except Exception as e:
            print(f"Error adding tag {tag_name} to image: {e}")
            return False
    
    def remove_tag_from_image(self, session: Session, image: Image, category: str, tag_name: str) -> bool:
        """Remove a tag from an image."""
        try:
            tag = session.query(Tag).filter_by(category=category, name=tag_name).first()
            if tag:
                image_tag = session.query(ImageTag).filter_by(
                    image_id=image.id, 
                    tag_id=tag.id
                ).first()
                if image_tag:
                    session.delete(image_tag)
                    return True
            return False
            
        except Exception as e:
            print(f"Error removing tag {tag_name} from image: {e}")
            return False
    
    def get_images_by_query(self, session: Session, query: str = None, 
                           limit: int = None, offset: int = None) -> List[Image]:
        """
        Get images matching a query.
        
        Args:
            session: Database session
            query: Tag-based query string (e.g., "people_tags:child1 AND event_tags:birthday")
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            List of Image objects
        """
        try:
            # Start with base query
            db_query = session.query(Image).filter(Image.is_corrupt == False)
            
            if query:
                # TODO: Implement query parsing in tag_manager.py
                # For now, return all non-corrupt images
                pass
                
            # Apply ordering
            db_query = db_query.order_by(Image.date_taken.desc(), Image.filename)
            
            # Apply limit and offset
            if offset:
                db_query = db_query.offset(offset)
            if limit:
                db_query = db_query.limit(limit)
                
            return db_query.all()
            
        except Exception as e:
            print(f"Error querying images: {e}")
            return []
    
    def get_image_tags(self, session: Session, image: Image) -> Dict[str, List[str]]:
        """
        Get all tags for an image organized by category.
        
        Returns:
            Dictionary with category as key and list of tag names as value
        """
        try:
            result = {category: [] for category in TAG_CATEGORIES}
            
            for image_tag in image.tags:
                tag = image_tag.tag
                if tag.category in result:
                    result[tag.category].append(tag.name)
            
            return result
            
        except Exception as e:
            print(f"Error getting tags for image: {e}")
            return {category: [] for category in TAG_CATEGORIES}
    
    def mark_directory_scanned(self, session: Session, directory_path: str, 
                              template_path: Optional[str] = None, 
                              image_count: int = 0) -> Directory:
        """Mark a directory as scanned and track the template used."""
        try:
            # Check if directory already tracked
            directory = session.query(Directory).filter_by(path=directory_path).first()
            
            if directory:
                # Update existing record
                directory.last_scanned = datetime.utcnow()
                directory.auto_tag_template_used = template_path
                directory.image_count = image_count
            else:
                # Create new record
                directory = Directory(
                    path=directory_path,
                    auto_tag_template_used=template_path,
                    image_count=image_count
                )
                session.add(directory)
                
            session.flush()
            return directory
            
        except Exception as e:
            print(f"Error marking directory as scanned: {e}")
            return None
    
    def get_duplicate_groups(self, session: Session) -> List[List[Image]]:
        """
        Get groups of images with matching perceptual hashes.
        
        Returns:
            List of lists, each inner list contains duplicate images
        """
        try:
            # Find images with duplicate pHashes
            duplicate_hashes = session.query(Image.phash).filter(
                Image.phash.isnot(None),
                Image.is_corrupt == False
            ).group_by(Image.phash).having(func.count(Image.id) > 1).all()
            
            duplicate_groups = []
            for (phash,) in duplicate_hashes:
                images = session.query(Image).filter_by(phash=phash).all()
                if len(images) > 1:
                    duplicate_groups.append(images)
                    
            return duplicate_groups
            
        except Exception as e:
            print(f"Error finding duplicate groups: {e}")
            return []
    
    def remove_missing_files(self, session: Session) -> int:
        """
        Remove images from database where the file no longer exists.
        
        Returns:
            Number of images removed
        """
        removed_count = 0
        try:
            images = session.query(Image).all()
            
            for image in images:
                if not os.path.exists(image.file_path):
                    session.delete(image)
                    removed_count += 1
                    
            session.commit()
            return removed_count
            
        except Exception as e:
            print(f"Error removing missing files: {e}")
            session.rollback()
            return 0
    
    def get_statistics(self, session: Session) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            stats = {}
            stats['total_images'] = session.query(Image).count()
            stats['corrupt_images'] = session.query(Image).filter(Image.is_corrupt == True).count()
            stats['reviewed_images'] = session.query(Image).filter(Image.tags_reviewed == True).count()
            stats['total_tags'] = session.query(Tag).count()
            stats['directories'] = session.query(Directory).count()
            
            # Tag counts by category
            for category in TAG_CATEGORIES:
                count = session.query(Tag).filter(Tag.category == category).count()
                stats[f'{category}_count'] = count
                
            return stats
            
        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}


def create_database(db_path: str) -> bool:
    """Create a new database file."""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        
        # Create engine and tables
        engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(engine)
        
        print(f"Database created: {db_path}")
        return True
        
    except Exception as e:
        print(f"Error creating database: {e}")
        return False