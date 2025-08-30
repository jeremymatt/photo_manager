"""
EXIF data extraction utilities.
Handles reading date, time, location, and camera information from image files.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS


def extract_datetime_from_exif(image: Image.Image) -> Optional[datetime]:
    """
    Extract date/time from EXIF data.
    
    Args:
        image: PIL Image object
        
    Returns:
        datetime object or None if not found
    """
    try:
        if hasattr(image, '_getexif') and image._getexif():
            exif = image._getexif()
            
            # Try different EXIF date fields in order of preference
            date_fields = ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']
            
            for field in date_fields:
                for tag_id, value in exif.items():
                    tag_name = TAGS.get(tag_id, tag_id)
                    if tag_name == field and value:
                        return _parse_exif_datetime(value)
        
        return None
        
    except Exception as e:
        print(f"Error extracting datetime from EXIF: {e}")
        return None


def extract_location_from_exif(image: Image.Image) -> Dict[str, Any]:
    """
    Extract GPS location data from EXIF.
    
    Args:
        image: PIL Image object
        
    Returns:
        Dictionary with latitude, longitude, and location info
    """
    location_data = {}
    
    try:
        if hasattr(image, '_getexif') and image._getexif():
            exif = image._getexif()
            
            # Look for GPS info
            gps_info = None
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if tag_name == 'GPSInfo':
                    gps_info = value
                    break
            
            if gps_info:
                gps_data = {}
                for key, value in gps_info.items():
                    gps_tag = GPSTAGS.get(key, key)
                    gps_data[gps_tag] = value
                
                # Extract coordinates
                lat = _convert_gps_coordinate(
                    gps_data.get('GPSLatitude'),
                    gps_data.get('GPSLatitudeRef')
                )
                lng = _convert_gps_coordinate(
                    gps_data.get('GPSLongitude'),
                    gps_data.get('GPSLongitudeRef')
                )
                
                if lat is not None and lng is not None:
                    location_data['latitude'] = lat
                    location_data['longitude'] = lng
                
                # Extract altitude if available
                altitude = gps_data.get('GPSAltitude')
                if altitude:
                    location_data['altitude'] = float(altitude)
        
        return location_data
        
    except Exception as e:
        print(f"Error extracting location from EXIF: {e}")
        return {}


def extract_camera_info(image: Image.Image) -> Dict[str, Any]:
    """
    Extract camera and shooting information from EXIF.
    
    Args:
        image: PIL Image object
        
    Returns:
        Dictionary with camera information
    """
    camera_info = {}
    
    try:
        if hasattr(image, '_getexif') and image._getexif():
            exif = image._getexif()
            
            # Map of EXIF tags to our field names
            camera_fields = {
                'Make': 'camera_make',
                'Model': 'camera_model',
                'ExposureTime': 'shutter_speed',
                'FNumber': 'aperture',
                'ISOSpeedRatings': 'iso',
                'FocalLength': 'focal_length',
                'Flash': 'flash',
                'WhiteBalance': 'white_balance'
            }
            
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if tag_name in camera_fields and value:
                    camera_info[camera_fields[tag_name]] = value
        
        return camera_info
        
    except Exception as e:
        print(f"Error extracting camera info from EXIF: {e}")
        return {}


def _parse_exif_datetime(date_string: str) -> Optional[datetime]:
    """
    Parse EXIF datetime string.
    
    Args:
        date_string: EXIF datetime string (e.g., "2024:06:15 14:30:25")
        
    Returns:
        datetime object or None if parsing failed
    """
    try:
        # EXIF datetime format: "YYYY:MM:DD HH:MM:SS"
        return datetime.strptime(date_string, "%Y:%m:%d %H:%M:%S")
        
    except ValueError:
        # Try alternative formats
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y:%m:%d %H:%M:%S.%f"  # With microseconds
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue
        
        print(f"Could not parse EXIF datetime: {date_string}")
        return None
        
    except Exception as e:
        print(f"Error parsing EXIF datetime '{date_string}': {e}")
        return None


def _convert_gps_coordinate(coord_tuple: tuple, ref: str) -> Optional[float]:
    """
    Convert GPS coordinate from EXIF format to decimal degrees.
    
    Args:
        coord_tuple: Tuple of (degrees, minutes, seconds) as fractions
        ref: Reference direction ('N', 'S', 'E', 'W')
        
    Returns:
        Decimal coordinate or None if conversion failed
    """
    try:
        if not coord_tuple or not ref:
            return None
        
        # Convert fractions to float
        degrees = float(coord_tuple[0])
        minutes = float(coord_tuple[1])
        seconds = float(coord_tuple[2])
        
        # Calculate decimal degrees
        decimal = degrees + (minutes / 60) + (seconds / 3600)
        
        # Apply direction (South and West are negative)
        if ref in ['S', 'W']:
            decimal = -decimal
        
        return decimal
        
    except Exception as e:
        print(f"Error converting GPS coordinate: {e}")
        return None


def get_image_orientation(image: Image.Image) -> int:
    """
    Get rotation needed to correct image orientation from EXIF.
    
    Args:
        image: PIL Image object
        
    Returns:
        Rotation degrees (0, 90, 180, 270)
    """
    try:
        if hasattr(image, '_getexif') and image._getexif():
            exif = image._getexif()
            
            for tag_id, value in exif.items():
                tag_name = TAGS.get(tag_id, tag_id)
                if tag_name == 'Orientation':
                    # EXIF orientation values to rotation mapping
                    orientations = {
                        1: 0,    # Normal
                        2: 0,    # Mirrored horizontal  
                        3: 180,  # Rotated 180
                        4: 180,  # Mirrored vertical
                        5: 90,   # Mirrored horizontal and rotated 90 CCW
                        6: 270,  # Rotated 90 CW
                        7: 270,  # Mirrored horizontal and rotated 90 CW  
                        8: 90    # Rotated 90 CCW
                    }
                    return orientations.get(value, 0)
        
        return 0
        
    except Exception as e:
        print(f"Error getting image orientation: {e}")
        return 0