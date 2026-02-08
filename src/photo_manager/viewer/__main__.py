"""Allow running the viewer as: python -m photo_manager.viewer"""

import sys
from photo_manager.viewer.app import main

sys.exit(main())
