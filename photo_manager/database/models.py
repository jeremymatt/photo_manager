"""
Database models for the photo manager application.
Defines the schema for images, tags, and their relationships.
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import os

Base = declarative_base()


class Image(Base):
    """Main image table storing file metadata and processing status."""
    __tablename__ = 'images'
    
    id = Column(Integer, primary_key=True)
    file_path = Column(String(1024), nullable=False, unique=True, index=True)
    filename = Column(String(255), nullable=False, index=True)
    
    # Hashing for duplicate detection
    phash = Column(String(16), index=True)  # Perceptual hash
    dhash = Column(String(16), index=True)  # Difference hash
    
    # File metadata
    file_size = Column(Integer)
    width = Column(Integer)
    height = Column(Integer)
    
    # Date information
    date_taken = Column(DateTime, index=True)  # From EXIF or filename
    date_added = Column(DateTime, default=datetime.utcnow, index=True)
    
    # Location information
    location_lat = Column(Float)
    location_lng = Column(Float) 
    location_name = Column(String(255))
    
    # Metadata
    photographer = Column(String(255))
    tags_reviewed = Column(Boolean, default=False, index=True)
    
    # Error handling
    is_corrupt = Column(Boolean, default=False, index=True)
    load_error = Column(Text)  # Store error message if image can't be loaded
    
    # Relationships
    tags = relationship("ImageTag", back_populates="image", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Image(id={self.id}, filename='{self.filename}', tags_reviewed={self.tags_reviewed})>"


class Tag(Base):
    """Tag definitions with categories."""
    __tablename__ = 'tags'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)  # favorites, to_delete, scene_tags, event_tags, people_tags
    
    # Ensure unique tag name within category
    __table_args__ = {'sqlite_autoincrement': True}
    
    # Relationships
    images = relationship("ImageTag", back_populates="tag", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Tag(id={self.id}, category='{self.category}', name='{self.name}')>"


class ImageTag(Base):
    """Many-to-many relationship between images and tags."""
    __tablename__ = 'image_tags'
    
    id = Column(Integer, primary_key=True)
    image_id = Column(Integer, ForeignKey('images.id'), nullable=False, index=True)
    tag_id = Column(Integer, ForeignKey('tags.id'), nullable=False, index=True)
    
    # Timestamp when tag was applied
    date_applied = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    image = relationship("Image", back_populates="tags")
    tag = relationship("Tag", back_populates="images")
    
    def __repr__(self):
        return f"<ImageTag(image_id={self.image_id}, tag_id={self.tag_id})>"


class Directory(Base):
    """Track which directories have been scanned."""
    __tablename__ = 'directories'
    
    id = Column(Integer, primary_key=True)
    path = Column(String(1024), nullable=False, unique=True, index=True)
    last_scanned = Column(DateTime, default=datetime.utcnow)
    auto_tag_template_used = Column(String(1024))  # Path to template file used
    image_count = Column(Integer, default=0)
    
    def __repr__(self):
        return f"<Directory(id={self.id}, path='{self.path}', image_count={self.image_count})>"


# Predefined tag categories
TAG_CATEGORIES = [
    'favorites',
    'to_delete', 
    'scene_tags',
    'event_tags',
    'people_tags'
]

# Helper function to get or create a tag
def get_or_create_tag(session, category, name):
    """Get existing tag or create new one."""
    tag = session.query(Tag).filter_by(category=category, name=name).first()
    if not tag:
        tag = Tag(category=category, name=name)
        session.add(tag)
        session.flush()  # Get the ID without committing
    return tag