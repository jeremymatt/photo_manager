"""Entry point for python -m photo_manager.organizer."""

import sys

from photo_manager.organizer.app import create_organizer_app

sys.exit(create_organizer_app())
