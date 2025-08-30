"""
Filename parsing utilities for extracting dates and metadata from filenames.
Handles various common filename formats for date extraction.
"""

import re
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path


def extract_datetime_from_filename(file_path: str) -> Optional[datetime]:
    """
    Extract datetime from filename using common patterns.
    
    Args:
        file_path: Full path to image file
        
    Returns:
        datetime object or None if no date found
    """
    filename = Path(file_path).stem  # Filename without extension
    
    # Common date/time patterns in filenames
    patterns = [
        # ISO format: 2024-06-28 17.29.53 or 2024-06-28_17-29-53
        r'(\d{4})[-_](\d{2})[-_](\d{2})[\s_.-](\d{2})[\s_.-](\d{2})[\s_.-](\d{2})',
        
        # Compact format: 20240628_172953 or 20210911_053849
        r'(\d{4})(\d{2})(\d{2})[\s_.-](\d{2})(\d{2})(\d{2})',
        
        # Date only: 2024-06-28 or 2024_06_28
        r'(\d{4})[-_](\d{2})[-_](\d{2})',
        
        # Date only compact: 20240628
        r'(\d{4})(\d{2})(\d{2})',
        
        # Camera format: IMG_20240628_172953
        r'IMG_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})',
        
        # Screenshot format: Screenshot_2024-06-28_17-29-53
        r'Screenshot_(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})',
        
        # WhatsApp format: WhatsApp Image 2024-06-28 at 17.29.53
        r'WhatsApp.*(\d{4})-(\d{2})-(\d{2}).*(\d{2})\.(\d{2})\.(\d{2})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, filename)
        if match:
            groups = match.groups()
            
            try:
                if len(groups) == 3:
                    # Date only
                    year, month, day = map(int, groups)
                    return datetime(year, month, day)
                elif len(groups) == 6:
                    # Date and time
                    year, month, day, hour, minute, second = map(int, groups)
                    return datetime(year, month, day, hour, minute, second)
                    
            except ValueError as e:
                print(f"Invalid date components in filename {filename}: {e}")
                continue
    
    return None


def extract_metadata_from_path(file_path: str, base_directory: str, 
                              template_patterns: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    Extract metadata from file path using template patterns.
    
    Args:
        file_path: Full path to image file
        base_directory: Base directory being scanned
        template_patterns: List of pattern configurations
        
    Returns:
        Dictionary with extracted metadata by category
    """
    extracted_data = {}
    
    try:
        # Get relative path from base directory
        rel_path = os.path.relpath(file_path, base_directory)
        
        for pattern_config in template_patterns:
            pattern = pattern_config.get('pattern', '')
            mapping = pattern_config.get('mapping', {})
            
            if pattern == 'none':
                continue
            
            # Convert template pattern to regex
            regex_pattern = _template_to_regex(pattern)
            
            match = re.match(regex_pattern, '/' + rel_path.replace('\\', '/'))
            if match:
                # Extract groups and map to categories
                groups = match.groups()
                group_names = _extract_group_names(pattern)
                
                for i, value in enumerate(groups):
                    if i < len(group_names) and value:
                        field_name = group_names[i]
                        category = mapping.get(field_name)
                        
                        if category:
                            if category not in extracted_data:
                                extracted_data[category] = []
                            
                            # Handle special cases
                            if field_name == 'year' and category == 'date_year':
                                # Store year as metadata, not tag
                                continue
                            elif '_tags' in category:
                                # Split multi-value tags
                                tags = _split_tag_value(value)
                                extracted_data[category].extend(tags)
                            else:
                                extracted_data[category] = [value]
                
                break  # Use first matching pattern
    
    except Exception as e:
        print(f"Error extracting metadata from path {file_path}: {e}")
    
    return extracted_data


def _template_to_regex(template: str) -> str:
    """
    Convert template pattern to regex.
    
    Args:
        template: Template string like "/{year}/{photographer}/{people}-{scene}*.{ext}"
        
    Returns:
        Regex pattern string
    """
    # Escape special regex characters except our placeholders
    escaped = re.escape(template)
    
    # Replace escaped placeholders with capture groups
    # {word} becomes named capture group
    pattern = re.sub(r'\\{(\w+)\\}', r'([^/]+)', escaped)
    
    # Handle wildcards
    pattern = pattern.replace('\\*', '.*')
    
    # Make it match the full path
    return '^' + pattern + '$'


def _extract_group_names(template: str) -> List[str]:
    """
    Extract placeholder names from template.
    
    Args:
        template: Template string
        
    Returns:
        List of placeholder names in order
    """
    return re.findall(r'{(\w+)}', template)


def _split_tag_value(value: str) -> List[str]:
    """
    Split a tag value that might contain multiple tags.
    
    Args:
        value: Tag value string
        
    Returns:
        List of individual tag names
    """
    # Split on common separators and clean up
    separators = [',', ';', '&', '+', '_and_', ' and ']
    
    tags = [value]
    for sep in separators:
        new_tags = []
        for tag in tags:
            new_tags.extend(part.strip() for part in tag.split(sep))
        tags = new_tags
    
    # Filter out empty strings and normalize
    return [tag.strip().lower() for tag in tags if tag.strip()]


def guess_photographer_from_path(file_path: str) -> Optional[str]:
    """
    Attempt to guess photographer from directory names.
    
    Args:
        file_path: Full path to image file
        
    Returns:
        Photographer name or None
    """
    try:
        # Look for common photographer indicators in path
        path_parts = Path(file_path).parts
        
        # Common patterns that might indicate photographer
        photographer_patterns = [
            r'(?:photos?[_\s]+by[_\s]+)?([A-Z][a-z]+(?:[_\s][A-Z][a-z]+)*)',  # "Photos by John Smith"
            r'([A-Z][a-z]+)[_\s]*(?:camera|photos?)',  # "John_Camera" or "John Photos"
            r'(?:taken[_\s]+by[_\s]+)?([A-Z][a-z]+(?:[_\s][A-Z][a-z]+)*)',   # "Taken by John"
        ]
        
        for part in reversed(path_parts):  # Start from deepest directory
            for pattern in photographer_patterns:
                match = re.search(pattern, part, re.IGNORECASE)
                if match:
                    return match.group(1).replace('_', ' ').title()
        
        return None
        
    except Exception as e:
        print(f"Error guessing photographer from path: {e}")
        return None


def validate_template_pattern(pattern: str) -> Tuple[bool, str]:
    """
    Validate that a template pattern is well-formed.
    
    Args:
        pattern: Template pattern string
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        if pattern == 'none':
            return True, ""
        
        # Check for balanced braces
        open_braces = pattern.count('{')
        close_braces = pattern.count('}')
        
        if open_braces != close_braces:
            return False, "Unmatched braces in pattern"
        
        # Extract placeholders
        placeholders = re.findall(r'{(\w+)}', pattern)
        
        if not placeholders:
            return False, "No placeholders found in pattern"
        
        # Check for valid placeholder names
        valid_placeholders = [
            'year', 'month', 'day', 'date', 'datetime',
            'photographer', 'people', 'scene', 'event',
            'ext', 'filename'
        ]
        
        invalid_placeholders = [p for p in placeholders if p not in valid_placeholders]
        if invalid_placeholders:
            return False, f"Invalid placeholders: {', '.join(invalid_placeholders)}"
        
        # Try to compile as regex
        try:
            regex = _template_to_regex(pattern)
            re.compile(regex)
        except re.error as e:
            return False, f"Invalid regex pattern: {e}"
        
        return True, ""
        
    except Exception as e:
        return False, f"Error validating pattern: {e}"


def extract_date_from_directory_name(directory_path: str) -> Optional[datetime]:
    """
    Extract date information from directory name.
    
    Args:
        directory_path: Path to directory
        
    Returns:
        datetime object or None if no date found
    """
    try:
        dir_name = os.path.basename(directory_path)
        
        # Patterns for directory names with dates
        date_patterns = [
            r'(\d{4})-(\d{2})-(\d{2})',     # 2024-06-28
            r'(\d{4})_(\d{2})_(\d{2})',     # 2024_06_28
            r'(\d{2})-(\d{2})-(\d{4})',     # 28-06-2024
            r'(\d{4})(\d{2})(\d{2})',       # 20240628
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, dir_name)
            if match:
                groups = match.groups()
                
                try:
                    if len(groups) == 3:
                        # Determine format
                        if len(groups[0]) == 4:  # Year first
                            year, month, day = map(int, groups)
                        else:  # Day first  
                            day, month, year = map(int, groups)
                        
                        return datetime(year, month, day)
                        
                except ValueError:
                    continue
        
        return None
        
    except Exception as e:
        print(f"Error extracting date from directory name: {e}")
        return None