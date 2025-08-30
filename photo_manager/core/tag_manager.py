"""
Tag management and query processing for the photo manager.
Handles tag operations, filtering, and boolean query parsing.
"""

import re
from typing import List, Dict, Any, Optional, Set, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, not_
from datetime import datetime

from ..database.models import Image, Tag, ImageTag, TAG_CATEGORIES


class TagManager:
    """Manages tag operations and queries."""
    
    def __init__(self, db_manager):
        """Initialize tag manager with database connection."""
        self.db_manager = db_manager
        self.copied_tags = {}  # For copy/paste tag functionality
    
    def add_tags_to_image(self, session: Session, image: Image, tags: Dict[str, List[str]]) -> bool:
        """
        Add multiple tags to an image.
        
        Args:
            session: Database session
            image: Image object
            tags: Dictionary mapping categories to lists of tag names
            
        Returns:
            True if successful
        """
        try:
            for category, tag_names in tags.items():
                if category not in TAG_CATEGORIES:
                    print(f"Invalid tag category: {category}")
                    continue
                    
                for tag_name in tag_names:
                    self.db_manager.add_tag_to_image(session, image, category, tag_name)
            
            return True
            
        except Exception as e:
            print(f"Error adding tags to image: {e}")
            return False
    
    def remove_tags_from_image(self, session: Session, image: Image, tags: Dict[str, List[str]]) -> bool:
        """Remove multiple tags from an image."""
        try:
            for category, tag_names in tags.items():
                for tag_name in tag_names:
                    self.db_manager.remove_tag_from_image(session, image, category, tag_name)
            
            return True
            
        except Exception as e:
            print(f"Error removing tags from image: {e}")
            return False
    
    def copy_image_tags(self, session: Session, image: Image):
        """Copy all tags from an image for pasting to others."""
        try:
            self.copied_tags = self.db_manager.get_image_tags(session, image)
            print(f"Copied {sum(len(tags) for tags in self.copied_tags.values())} tags")
            
        except Exception as e:
            print(f"Error copying tags: {e}")
    
    def paste_tags_to_image(self, session: Session, image: Image) -> bool:
        """Paste previously copied tags to an image."""
        try:
            if not self.copied_tags:
                print("No tags copied")
                return False
            
            success = self.add_tags_to_image(session, image, self.copied_tags)
            if success:
                print(f"Pasted {sum(len(tags) for tags in self.copied_tags.values())} tags")
            
            return success
            
        except Exception as e:
            print(f"Error pasting tags: {e}")
            return False
    
    def get_all_tags_by_category(self, session: Session) -> Dict[str, List[str]]:
        """Get all available tags organized by category."""
        try:
            result = {category: [] for category in TAG_CATEGORIES}
            
            tags = session.query(Tag).order_by(Tag.category, Tag.name).all()
            
            for tag in tags:
                if tag.category in result:
                    result[tag.category].append(tag.name)
            
            return result
            
        except Exception as e:
            print(f"Error getting all tags: {e}")
            return {category: [] for category in TAG_CATEGORIES}
    
    def search_tags(self, session: Session, search_term: str, category: Optional[str] = None) -> List[Tag]:
        """
        Search for tags by name.
        
        Args:
            session: Database session
            search_term: Text to search for
            category: Optional category filter
            
        Returns:
            List of matching tags
        """
        try:
            query = session.query(Tag).filter(Tag.name.like(f'%{search_term}%'))
            
            if category:
                query = query.filter(Tag.category == category)
            
            return query.order_by(Tag.category, Tag.name).all()
            
        except Exception as e:
            print(f"Error searching tags: {e}")
            return []
    
    def parse_query(self, query_string: str) -> Optional[Any]:
        """
        Parse boolean query string into SQLAlchemy query conditions.
        
        Args:
            query_string: Query like "(people_tags:child1 OR people_tags:child2) AND event_tags:birthday"
            
        Returns:
            SQLAlchemy condition object or None if parsing failed
        """
        try:
            if not query_string.strip():
                return None
            
            # Tokenize the query
            tokens = self._tokenize_query(query_string)
            
            # Parse into condition tree
            condition = self._parse_query_tokens(tokens)
            
            return condition
            
        except Exception as e:
            print(f"Error parsing query '{query_string}': {e}")
            return None
    
    def _tokenize_query(self, query: str) -> List[str]:
        """
        Tokenize query string into components.
        
        Args:
            query: Query string
            
        Returns:
            List of tokens
        """
        # Simple tokenizer - splits on spaces, preserves parentheses and operators
        # Handle quoted strings and category:value pairs
        
        tokens = []
        current_token = ""
        in_quotes = False
        
        i = 0
        while i < len(query):
            char = query[i]
            
            if char == '"' and (i == 0 or query[i-1] != '\\'):
                in_quotes = not in_quotes
                current_token += char
            elif in_quotes:
                current_token += char
            elif char in '()':
                if current_token.strip():
                    tokens.append(current_token.strip())
                    current_token = ""
                tokens.append(char)
            elif char.isspace():
                if current_token.strip():
                    tokens.append(current_token.strip())
                    current_token = ""
            else:
                current_token += char
            
            i += 1
        
        if current_token.strip():
            tokens.append(current_token.strip())
        
        return tokens
    
    def _parse_query_tokens(self, tokens: List[str]) -> Any:
        """
        Parse tokenized query into SQLAlchemy conditions.
        
        Args:
            tokens: List of query tokens
            
        Returns:
            SQLAlchemy condition
        """
        # Use class methods for better organization
        result, pos = self._parse_expression(tokens, 0)
        
        if pos < len(tokens):
            raise ValueError(f"Unexpected tokens after query: {tokens[pos:]}")
        
        return result
    
    def _parse_expression(self, tokens: List[str], pos: int) -> tuple:
        """Parse a boolean expression (handles AND/OR)."""
        left, pos = self._parse_term(tokens, pos)
        
        while pos < len(tokens) and tokens[pos].upper() in ['AND', 'OR']:
            operator = tokens[pos].upper()
            pos += 1
            right, pos = self._parse_term(tokens, pos)
            
            if operator == 'AND':
                left = and_(left, right)
            else:  # OR
                left = or_(left, right)
        
        return left, pos
    
    def _parse_term(self, tokens: List[str], pos: int) -> tuple:
        """Parse a term (condition or parenthesized expression)."""
        if pos >= len(tokens):
            raise ValueError("Unexpected end of query")
        
        token = tokens[pos]
        
        if token == '(':
            pos += 1
            expr, pos = self._parse_expression(tokens, pos)
            if pos >= len(tokens) or tokens[pos] != ')':
                raise ValueError("Missing closing parenthesis")
            return expr, pos + 1
        
        elif token.upper() == 'NOT':
            pos += 1
            expr, pos = self._parse_term(tokens, pos)
            return not_(expr), pos
        
        else:
            # Should be a category:value condition
            condition = self._parse_condition(token)
            return condition, pos + 1
    
    def _parse_condition(self, condition_str: str) -> Any:
        """
        Parse a single condition like "people_tags:child1" into SQLAlchemy condition.
        
        Args:
            condition_str: Condition string
            
        Returns:
            SQLAlchemy condition
        """
        try:
            if ':' not in condition_str:
                raise ValueError(f"Invalid condition format: {condition_str}")
            
            category, value = condition_str.split(':', 1)
            category = category.strip()
            value = value.strip().strip('"')  # Remove quotes if present
            
            # Special cases for boolean fields
            if category == 'tags_reviewed':
                bool_value = value.lower() in ['true', '1', 'yes']
                return Image.tags_reviewed == bool_value
            
            elif category == 'favorites':
                bool_value = value.lower() in ['true', '1', 'yes']
                # Check if image has favorite tag
                return Image.tags.any(and_(
                    ImageTag.tag.has(Tag.category == 'favorites'),
                    ImageTag.tag.has(Tag.name == 'true' if bool_value else 'false')
                ))
            
            elif category == 'to_delete':
                bool_value = value.lower() in ['true', '1', 'yes']
                return Image.tags.any(and_(
                    ImageTag.tag.has(Tag.category == 'to_delete'),
                    ImageTag.tag.has(Tag.name == 'true' if bool_value else 'false')
                ))
            
            elif category in TAG_CATEGORIES:
                # Tag-based condition
                return Image.tags.any(and_(
                    ImageTag.tag.has(Tag.category == category),
                    ImageTag.tag.has(Tag.name == value)
                ))
            
            elif category == 'date_taken':
                # Date-based queries
                return self._parse_date_condition(value)
            
            elif category == 'photographer':
                return Image.photographer == value
            
            else:
                raise ValueError(f"Unknown query category: {category}")
                
        except Exception as e:
            print(f"Error parsing condition '{condition_str}': {e}")
            # Return condition that matches nothing
            return Image.id == -1
    
    def _parse_date_condition(self, date_value: str) -> Any:
        """Parse date condition like '2024' or '2024-06' into SQLAlchemy condition."""
        try:
            # Year only
            if re.match(r'^\d{4}$', date_value):
                year = int(date_value)
                return and_(
                    Image.date_taken >= datetime(year, 1, 1),
                    Image.date_taken < datetime(year + 1, 1, 1)
                )
            
            # Year-month
            elif re.match(r'^\d{4}-\d{2}$', date_value):
                year, month = map(int, date_value.split('-'))
                start_date = datetime(year, month, 1)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1)
                else:
                    end_date = datetime(year, month + 1, 1)
                
                return and_(
                    Image.date_taken >= start_date,
                    Image.date_taken < end_date
                )
            
            # Full date
            elif re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
                year, month, day = map(int, date_value.split('-'))
                start_date = datetime(year, month, day)
                end_date = datetime(year, month, day, 23, 59, 59)
                
                return and_(
                    Image.date_taken >= start_date,
                    Image.date_taken <= end_date
                )
            
            else:
                raise ValueError(f"Invalid date format: {date_value}")
                
        except Exception as e:
            print(f"Error parsing date condition '{date_value}': {e}")
            return Image.id == -1
    
    def get_images_by_query(self, session: Session, query_string: str) -> List[Image]:
        """
        Get images matching a query string.
        
        Args:
            session: Database session
            query_string: Boolean query string
            
        Returns:
            List of matching images
        """
        try:
            if not query_string.strip():
                # Return all non-corrupt images
                return session.query(Image).filter(Image.is_corrupt == False).all()
            
            # Parse query
            condition = self.parse_query(query_string)
            if condition is None:
                return []
            
            # Execute query
            return session.query(Image).filter(
                and_(Image.is_corrupt == False, condition)
            ).order_by(Image.date_taken.desc(), Image.filename).all()
            
        except Exception as e:
            print(f"Error executing query '{query_string}': {e}")
            return []
    
    def toggle_tag(self, session: Session, image: Image, category: str, tag_name: str) -> bool:
        """
        Toggle a tag on an image (add if not present, remove if present).
        
        Args:
            session: Database session
            image: Image object
            category: Tag category
            tag_name: Tag name
            
        Returns:
            True if tag was added, False if removed
        """
        try:
            # Check if tag already exists
            existing_tag = session.query(Tag).filter_by(category=category, name=tag_name).first()
            
            if existing_tag:
                existing_image_tag = session.query(ImageTag).filter_by(
                    image_id=image.id,
                    tag_id=existing_tag.id
                ).first()
                
                if existing_image_tag:
                    # Remove tag
                    session.delete(existing_image_tag)
                    return False
            
            # Add tag
            self.db_manager.add_tag_to_image(session, image, category, tag_name)
            return True
            
        except Exception as e:
            print(f"Error toggling tag: {e}")
            return False
    
    def get_tag_suggestions(self, session: Session, partial_name: str, category: str) -> List[str]:
        """
        Get tag name suggestions based on partial input.
        
        Args:
            session: Database session
            partial_name: Partial tag name
            category: Tag category
            
        Returns:
            List of suggested tag names
        """
        try:
            suggestions = session.query(Tag.name).filter(
                Tag.category == category,
                Tag.name.like(f'%{partial_name}%')
            ).distinct().order_by(Tag.name).limit(10).all()
            
            return [s[0] for s in suggestions]
            
        except Exception as e:
            print(f"Error getting tag suggestions: {e}")
            return []
    
    def bulk_tag_operation(self, session: Session, images: List[Image], 
                          operation: str, tags: Dict[str, List[str]]) -> int:
        """
        Apply tag operation to multiple images.
        
        Args:
            session: Database session
            images: List of images to operate on
            operation: 'add' or 'remove'
            tags: Tags to add/remove
            
        Returns:
            Number of images successfully processed
        """
        try:
            processed = 0
            
            for image in images:
                if operation == 'add':
                    success = self.add_tags_to_image(session, image, tags)
                elif operation == 'remove':
                    success = self.remove_tags_from_image(session, image, tags)
                else:
                    print(f"Unknown operation: {operation}")
                    continue
                
                if success:
                    processed += 1
            
            return processed
            
        except Exception as e:
            print(f"Error in bulk tag operation: {e}")
            return 0
    
    def mark_images_reviewed(self, session: Session, images: List[Image]) -> int:
        """
        Mark multiple images as having their tags reviewed.
        
        Args:
            session: Database session
            images: List of images to mark
            
        Returns:
            Number of images marked
        """
        try:
            count = 0
            for image in images:
                image.tags_reviewed = True
                count += 1
            
            return count
            
        except Exception as e:
            print(f"Error marking images as reviewed: {e}")
            return 0
    
    def get_unreviewed_images(self, session: Session, limit: Optional[int] = None) -> List[Image]:
        """Get images that haven't been reviewed yet."""
        try:
            query = session.query(Image).filter(
                Image.tags_reviewed == False,
                Image.is_corrupt == False
            ).order_by(Image.date_added)
            
            if limit:
                query = query.limit(limit)
            
            return query.all()
            
        except Exception as e:
            print(f"Error getting unreviewed images: {e}")
            return []


class QueryBuilder:
    """Helper class for building complex queries programmatically."""
    
    def __init__(self):
        self.conditions = []
    
    def add_tag_condition(self, category: str, tag_name: str, operator: str = 'AND'):
        """Add a tag-based condition."""
        condition_str = f"{category}:{tag_name}"
        
        if self.conditions and operator:
            self.conditions.append(operator.upper())
        
        self.conditions.append(condition_str)
        return self
    
    def add_date_condition(self, date_value: str, operator: str = 'AND'):
        """Add a date-based condition."""
        condition_str = f"date_taken:{date_value}"
        
        if self.conditions and operator:
            self.conditions.append(operator.upper())
        
        self.conditions.append(condition_str)
        return self
    
    def add_group_start(self):
        """Start a parenthesized group."""
        self.conditions.append('(')
        return self
    
    def add_group_end(self):
        """End a parenthesized group."""
        self.conditions.append(')')
        return self
    
    def build(self) -> str:
        """Build the final query string."""
        return ' '.join(self.conditions)
    
    def clear(self):
        """Clear all conditions."""
        self.conditions = []
        return self


def validate_query_syntax(query_string: str) -> Tuple[bool, str]:
    """
    Validate query syntax without executing it.
    
    Args:
        query_string: Query string to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if not query_string.strip():
            return True, ""
        
        # Check balanced parentheses
        paren_count = 0
        for char in query_string:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
                if paren_count < 0:
                    return False, "Unmatched closing parenthesis"
        
        if paren_count != 0:
            return False, "Unmatched opening parenthesis"
        
        # Check for valid category:value pairs
        # Simple regex to find category:value patterns
        conditions = re.findall(r'(\w+):(["\w\s-]+)', query_string)
        
        valid_categories = set(TAG_CATEGORIES + ['date_taken', 'photographer', 'tags_reviewed', 'favorites', 'to_delete'])
        
        for category, value in conditions:
            if category not in valid_categories:
                return False, f"Invalid category: {category}"
        
        # Check for valid operators
        operators = re.findall(r'\b(AND|OR|NOT)\b', query_string, re.IGNORECASE)
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validating query: {e}"


def build_favorite_query() -> str:
    """Build query for favorite images."""
    return "favorites:true"


def build_unreviewed_query() -> str:
    """Build query for unreviewed images."""
    return "tags_reviewed:false"


def build_deletion_queue_query() -> str:
    """Build query for images marked for deletion."""
    return "to_delete:true"