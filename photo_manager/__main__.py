"""
Main module for running photo_manager as a package.
Enables 'python -m photo_manager' execution.
"""

import sys
from .main import main

if __name__ == '__main__':
    sys.exit(main())