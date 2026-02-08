"""EXIF data extraction from image files."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS


@dataclass
class ExifData:
    """Extracted EXIF metadata from an image."""

    datetime_original: datetime | None = None
    datetime_digitized: datetime | None = None
    datetime_modified: datetime | None = None
    orientation: int = 1  # 1 = normal, values 1-8
    gps_latitude: float | None = None
    gps_longitude: float | None = None
    width: int | None = None
    height: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)


def extract_exif(filepath: str | Path) -> ExifData:
    """Extract EXIF data from an image file.

    Returns an ExifData object with parsed fields. Non-EXIF images
    (PNG, GIF, etc.) will return an ExifData with only width/height populated.
    """
    filepath = Path(filepath)
    result = ExifData()

    try:
        with Image.open(filepath) as img:
            result.width = img.width
            result.height = img.height

            exif_raw = img.getexif()
            if not exif_raw:
                return result

            # Decode standard EXIF tags
            decoded: dict[str, Any] = {}
            for tag_id, value in exif_raw.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                decoded[tag_name] = value

            result.raw = decoded

            # Orientation
            if "Orientation" in decoded:
                try:
                    result.orientation = int(decoded["Orientation"])
                except (ValueError, TypeError):
                    pass

            # DateTime fields
            result.datetime_original = _parse_exif_datetime(
                decoded.get("DateTimeOriginal")
            )
            result.datetime_digitized = _parse_exif_datetime(
                decoded.get("DateTimeDigitized")
            )
            result.datetime_modified = _parse_exif_datetime(
                decoded.get("DateTime")
            )

            # GPS data from IFD
            gps_ifd = exif_raw.get_ifd(0x8825)
            if gps_ifd:
                gps_decoded = {}
                for tag_id, value in gps_ifd.items():
                    tag_name = GPSTAGS.get(tag_id, str(tag_id))
                    gps_decoded[tag_name] = value

                result.gps_latitude = _convert_gps_coord(
                    gps_decoded.get("GPSLatitude"),
                    gps_decoded.get("GPSLatitudeRef"),
                )
                result.gps_longitude = _convert_gps_coord(
                    gps_decoded.get("GPSLongitude"),
                    gps_decoded.get("GPSLongitudeRef"),
                )

    except Exception:
        # If we can't read the image at all, return empty ExifData
        pass

    return result


def get_oriented_image(filepath: str | Path) -> Image.Image:
    """Open an image and apply EXIF orientation correction."""
    img = Image.open(filepath)
    exif_raw = img.getexif()
    if exif_raw:
        orientation = exif_raw.get(0x0112)  # Orientation tag
        if orientation:
            img = _apply_orientation(img, orientation)
    return img


def _apply_orientation(img: Image.Image, orientation: int) -> Image.Image:
    """Apply EXIF orientation transform to an image."""
    transforms = {
        2: (Image.Transpose.FLIP_LEFT_RIGHT,),
        3: (Image.Transpose.ROTATE_180,),
        4: (Image.Transpose.FLIP_TOP_BOTTOM,),
        5: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_90),
        6: (Image.Transpose.ROTATE_270,),
        7: (Image.Transpose.FLIP_LEFT_RIGHT, Image.Transpose.ROTATE_270),
        8: (Image.Transpose.ROTATE_90,),
    }
    ops = transforms.get(orientation, ())
    for op in ops:
        img = img.transpose(op)
    return img


def _parse_exif_datetime(value: Any) -> datetime | None:
    """Parse EXIF datetime string (format: 'YYYY:MM:DD HH:MM:SS')."""
    if not value or not isinstance(value, str):
        return None
    formats = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue
    return None


def _convert_gps_coord(
    coord_tuple: Any, ref: str | None
) -> float | None:
    """Convert GPS coordinates from DMS (degrees, minutes, seconds) to decimal."""
    if coord_tuple is None or ref is None:
        return None
    try:
        degrees = float(coord_tuple[0])
        minutes = float(coord_tuple[1])
        seconds = float(coord_tuple[2])
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if ref in ("S", "W"):
            decimal = -decimal
        return decimal
    except (TypeError, IndexError, ValueError):
        return None
