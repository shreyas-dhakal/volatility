"""Domain tests use an isolated SQLite database and Clerk-backed request identity."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    SOURCE_TOKEN_ENCRYPTION_KEY="test-source-token-encryption-key",
)

import pytest
from galvanise.dependencies import get_current_user
from galvanise.main import app


@pytest.fixture(autouse=True)
def clear_identity_overrides():
    app.dependency_overrides.pop(get_current_user, None)
    yield
    app.dependency_overrides.pop(get_current_user, None)
