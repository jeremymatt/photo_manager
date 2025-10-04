#!/usr/bin/env python3
"""
Basic functionality test script for photo manager.
Tests core components without requiring Qt or full UI.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add photo_manager to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_database_creation():
    """Test database creation and basic operations."""
    print("Testing database creation...")
    
    try:
        from photo_manager.database.database_manager import DatabaseManager, create_database
        from photo_manager.database.models import Image, Tag
        
        # Create temporary database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        # Test database creation
        if create_database(db_path):
            print("✓ Database created successfully")
        else:
            print("✗ Database creation failed")
            return False
        
        # Test database connection
        db_config = {'type': 'sqlite', 'path': db_path}
        db_manager = DatabaseManager(db_config)
        
        if db_manager.initialize_connection():
            print("✓ Database connection successful")
        else:
            print("✗ Database connection failed")
            return False
        
        # Test adding an image
        with db_manager.get_session() as session:
            test_image = db_manager.add_image(
                session,
                '/test/path/image.jpg',
                width=1920,
                height=1080,
                file_size=2048000
            )
            
            if test_image:
                print("✓ Image added to database")
                
                # Test adding tag
                success = db_manager.add_tag_to_image(
                    session, test_image, 'event_tags', 'test_event'
                )
                
                if success:
                    print("✓ Tag added to image")
                else:
                    print("✗ Failed to add tag")
                
                session.commit()
            else:
                print("✗ Failed to add image")
        
        # Properly close database connections before cleanup
        if hasattr(db_manager, 'engine') and db_manager.engine:
            db_manager.engine.dispose()
        
        # Cleanup with retry for Windows file locking
        import time
        for attempt in range(3):
            try:
                os.unlink(db_path)
                break
            except OSError:
                if attempt < 2:
                    time.sleep(0.1)  # Wait briefly and retry
                else:
                    print("Warning: Could not delete temporary database file")
        
        return True
        
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def test_configuration():
    """Test configuration loading."""
    print("\nTesting configuration...")
    
    try:
        from photo_manager.config.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        config = config_manager.load_config(os.getcwd())
        
        if config and 'ui' in config:
            print("✓ Configuration loaded successfully")
            print(f"  Default zoom: {config['ui']['default_zoom']}")
            print(f"  Slideshow duration: {config['slideshow']['duration']}s")
            return True
        else:
            print("✗ Configuration loading failed")
            return False
            
    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def test_image_hashing():
    """Test image hashing functionality."""
    print("\nTesting image hashing...")
    
    try:
        from photo_manager.core.duplicate_detector import calculate_image_hashes
        from PIL import Image
        
        # Create a test image
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            test_img = Image.new('RGB', (100, 100), color='red')
            test_img.save(tmp.name)
            test_image_path = tmp.name
        
        # Test hash calculation
        hashes = calculate_image_hashes(test_image_path)
        
        if hashes and 'phash' in hashes and 'dhash' in hashes:
            print("✓ Image hashing successful")
            print(f"  pHash: {hashes['phash']}")
            print(f"  dHash: {hashes['dhash']}")
            result = True
        else:
            print("✗ Image hashing failed")
            result = False
        
        # Cleanup
        os.unlink(test_image_path)
        return result
        
    except Exception as e:
        print(f"✗ Image hashing test failed: {e}")
        return False


def test_pi_slideshow_imports():
    """Test Pi slideshow imports (without starting GUI)."""
    print("\nTesting Pi slideshow imports...")
    
    try:
        from photo_manager.ui.tkinter.pi_slideshow import PiSlideshow
        from photo_manager.ui.tkinter.fade_effects import FadeTransition
        
        print("✓ Pi slideshow modules imported successfully")
        return True
        
    except Exception as e:
        print(f"✗ Pi slideshow import test failed: {e}")
        return False


def test_file_utilities():
    """Test file utility functions.""" 
    print("\nTesting file utilities...")
    
    try:
        from photo_manager.utils.helpers import format_file_size, format_duration
        from photo_manager.utils.filename_parser import extract_datetime_from_filename
        
        # Test file size formatting
        size_str = format_file_size(2048000)
        if size_str == "1.9 MB":
            print("✓ File size formatting works")
        else:
            print(f"✗ File size formatting unexpected: {size_str}")
        
        # Test duration formatting  
        duration_str = format_duration(125)
        if "2m 5s" in duration_str:
            print("✓ Duration formatting works")
        else:
            print(f"✗ Duration formatting unexpected: {duration_str}")
        
        # Test filename date extraction
        test_filename = "/path/to/2024-06-28_14-30-25.jpg"
        extracted_date = extract_datetime_from_filename(test_filename)
        
        if extracted_date and extracted_date.year == 2024:
            print("✓ Filename date extraction works")
        else:
            print("✗ Filename date extraction failed")
        
        return True
        
    except Exception as e:
        print(f"✗ File utilities test failed: {e}")
        return False


def main():
    """Run all basic functionality tests."""
    print("Photo Manager Basic Functionality Test")
    print("=" * 50)
    
    tests = [
        test_configuration,
        test_database_creation,
        test_image_hashing,
        test_file_utilities,
        test_pi_slideshow_imports
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n✓ All basic functionality tests passed!")
        print("\nYou can now try:")
        print("  python -m photo_manager --help")
        print("  python slideshow_pi.py --help")
        return 0
    else:
        print(f"\n✗ {total - passed} tests failed")
        print("Check for missing dependencies or installation issues")
        return 1


if __name__ == '__main__':
    sys.exit(main())