"""Domain fixtures trust only isolated identities; real SDK tests stay separate."""

import os

os.environ.update(APP_ENV="test", DATABASE_URL="sqlite://")
import pytest
from fastapi import HTTPException
from galvanise import dependencies
from galvanise.models import User


@pytest.fixture(autouse=True)
def external_identity_boundary(request, monkeypatch):
    if request.node.path.name == "test_clerk_auth.py":
        return

    def verified(request):
        value = request.headers.get("authorization", "")
        if not value.startswith("Bearer isolated:"):
            raise HTTPException(401, "Sign in required")
        return value.removeprefix("Bearer isolated:")

    def resolved(db, subject):
        user = db.get(User, subject)
        if not user or not user.clerk_user_id:
            raise HTTPException(401, "Sign in required")
        return user

    monkeypatch.setattr(dependencies, "verified_subject", verified)
    monkeypatch.setattr(dependencies, "resolve_user", resolved)
