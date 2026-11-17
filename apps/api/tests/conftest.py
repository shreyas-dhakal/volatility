"""Existing domain tests exercise legacy fixtures in an isolated test database.

Clerk boundary tests switch mode explicitly and verify real signatures. No test
loads developer environment files or connects to the running application DB.
"""

import os

os.environ.update(APP_ENV="test", DATABASE_URL="sqlite://", AUTH_MODE="legacy")
