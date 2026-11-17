"""Migration tests never connect to an application database or Clerk instance."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    AUTH_SECRET="isolated-test-secret-that-is-at-least-32-characters",
    AUTO_CREATE_TABLES="true",
)
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from galvanise.database import Base, SessionLocal, engine
from galvanise.models import User, Project, Account
from galvanise.security import hasher, encrypt, decrypt
from galvanise import clerk_identity, clerk_import


class Provider:
    def __init__(self):
        self.rows = {}
        self.created = []
        self.fail_update = False
        self.timeout_once = False

    def get(self, subject):
        return self.rows[subject]

    def update(self, subject, external_id):
        if self.fail_update:
            raise TimeoutError()
        self.rows[subject].external_id = external_id

    def find(self, external_id):
        return [row for row in self.rows.values() if row.external_id == external_id]

    def create(self, **payload):
        self.created.append(payload)
        row = remote(
            f"user_{len(self.rows) + 1}",
            payload["email_address"][0],
            payload["external_id"],
        )
        self.rows[row.id] = row
        if self.timeout_once:
            self.timeout_once = False
            raise TimeoutError()
        return row


def remote(
    subject="user_new", email="new@example.com", external_id=None, verified=True
):
    return NS(
        id=subject,
        external_id=external_id,
        first_name="New",
        last_name=None,
        banned=False,
        locked=False,
        primary_email_address_id="email_1",
        email_addresses=[
            NS(
                id="email_1",
                email_address=email,
                verification=NS(status="verified" if verified else "unverified"),
            )
        ],
    )


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def test_import_preserves_owner_hash_and_encrypted_source():
    provider = Provider()
    with SessionLocal() as db:
        user = User(
            id="legacy-uuid",
            name="Owner",
            email="owner@example.com",
            password_hash=hasher.hash("test-password-123"),
        )
        db.add(user)
        db.flush()
        db.add_all(
            [
                Project(user_id=user.id, name="Private"),
                Account(
                    user_id=user.id,
                    github_id="123",
                    token_ciphertext=encrypt("synthetic-source-token"),
                ),
            ]
        )
        db.commit()
        result = clerk_import.import_users(
            db, provider, apply=True, sleep=lambda _: None
        )
        assert result == {"total": 1, "ready": 1, "blocked": 0, "migrated": 1}
        assert db.scalar(select(Project)).user_id == "legacy-uuid"
        assert (
            decrypt(db.scalar(select(Account)).token_ciphertext)
            == "synthetic-source-token"
        )
        assert user.clerk_user_id == "user_1"
        payload = provider.created[0]
        assert payload["external_id"] == "legacy-uuid"
        assert payload["password_digest"] == user.password_hash
        assert payload["password_hasher"] == "argon2id"
        assert payload["email_address_identification_status"] == ["reserved"]


def test_dry_run_never_calls_clerk_or_writes_mapping():
    with SessionLocal() as db:
        user = User(
            name="A",
            email="a@example.com",
            password_hash=hasher.hash("test-password-123"),
        )
        db.add(user)
        db.commit()
        result = clerk_import.import_users(db, None, apply=False)
        assert result["ready"] == 1 and result["migrated"] == 0
        assert user.clerk_user_id is None


def test_unsupported_hash_blocks_before_any_import():
    provider = Provider()
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    name="A",
                    email="a@example.com",
                    password_hash=hasher.hash("test-password-123"),
                ),
                User(name="B", email="b@example.com", password_hash="unknown"),
            ]
        )
        db.commit()
        assert clerk_import.import_users(db, provider, apply=True)["blocked"] == 1
        assert not provider.created


def test_github_only_import_omits_password_and_can_resume_after_timeout():
    provider = Provider()
    provider.timeout_once = True
    with SessionLocal() as db:
        user = User(name="A", email="a@example.com")
        db.add(user)
        db.flush()
        db.add(
            Account(
                user_id=user.id, github_id="1", token_ciphertext=encrypt("synthetic")
            )
        )
        db.commit()
        clerk_import.import_users(db, provider, apply=True, sleep=lambda _: None)
        assert len(provider.created) == 1
        assert "password_digest" not in provider.created[0]
        assert provider.created[0]["skip_password_requirement"] is True
        assert user.clerk_user_id == "user_1"
        clerk_import.import_users(db, provider, apply=True, sleep=lambda _: None)
        assert len(provider.created) == 1


def test_import_refuses_existing_external_id_with_different_email():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "other@example.com", "legacy")
    with SessionLocal() as db:
        db.add(
            User(
                id="legacy",
                name="A",
                email="a@example.com",
                password_hash=hasher.hash("test-password-123"),
            )
        )
        db.commit()
        with pytest.raises(clerk_import.MigrationConflict):
            clerk_import.import_users(db, provider, apply=True, sleep=lambda _: None)
        assert db.get(User, "legacy").clerk_user_id is None


def test_imported_subject_keeps_local_uuid():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "owner@example.com", "legacy")
    with SessionLocal() as db:
        db.add(
            User(
                id="legacy",
                clerk_user_id="user_old",
                name="Owner",
                email="owner@example.com",
            )
        )
        db.commit()
        assert clerk_identity.resolve_user(db, "user_old", provider).id == "legacy"


def test_new_user_is_provisioned_once_and_external_id_is_stable():
    provider = Provider()
    provider.rows["user_new"] = remote()
    with SessionLocal() as db:
        user = clerk_identity.resolve_user(db, "user_new", provider)
        assert user.clerk_user_id == "user_new"
        assert provider.get("user_new").external_id == user.id
        assert clerk_identity.resolve_user(db, "user_new", provider).id == user.id
        assert len(db.scalars(select(User)).all()) == 1


def test_new_subject_cannot_claim_existing_email():
    provider = Provider()
    provider.rows["user_new"] = remote(email="owner@example.com")
    with SessionLocal() as db:
        db.add(User(id="legacy", name="Owner", email="owner@example.com"))
        db.commit()
        with pytest.raises(HTTPException) as e:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert e.value.status_code == 409
        assert db.get(User, "legacy").clerk_user_id is None


def test_unverified_new_user_cannot_be_provisioned():
    provider = Provider()
    provider.rows["user_new"] = remote(verified=False)
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert e.value.status_code == 403
        assert not db.scalars(select(User)).all()


def test_failed_external_id_sync_denies_access_then_reconciles_same_user():
    provider = Provider()
    provider.rows["user_new"] = remote()
    provider.fail_update = True
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert e.value.status_code == 503
        original = db.scalar(select(User)).id
        provider.fail_update = False
        assert clerk_identity.resolve_user(db, "user_new", provider).id == original
        assert provider.get("user_new").external_id == original


def test_banned_user_is_denied_even_with_mapping():
    provider = Provider()
    provider.rows["user_new"] = remote()
    provider.rows["user_new"].banned = True
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as e:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert e.value.status_code == 401


def test_rate_limit_is_retried_and_checkpoint_reconciled():
    class RateLimited(Provider):
        attempts = 0

        def find(self, external_id):
            self.attempts += 1
            if self.attempts == 1:
                error = RuntimeError("rate limited")
                error.status_code = 429
                error.raw_response = NS(headers={"retry-after": "3"})
                raise error
            return super().find(external_id)

    provider = RateLimited()
    delays = []
    with SessionLocal() as db:
        db.add(
            User(
                name="A",
                email="a@example.com",
                password_hash=hasher.hash("test-password-123"),
            )
        )
        db.commit()
        assert (
            clerk_import.import_users(db, provider, apply=True, sleep=delays.append)[
                "migrated"
            ]
            == 1
        )
        assert delays == [3]
        assert len(provider.created) == 1


def test_import_conflicting_subject_cannot_reassign_another_owner():
    provider = Provider()
    provider.rows["user_1"] = remote("user_1", "owner@example.com", "legacy")
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id="legacy",
                    name="Owner",
                    email="owner@example.com",
                    password_hash=hasher.hash("test-password-123"),
                ),
                User(
                    id="other",
                    clerk_user_id="user_1",
                    name="Other",
                    email="other@example.com",
                    password_hash=hasher.hash("test-password-123"),
                ),
            ]
        )
        db.commit()
        with pytest.raises(clerk_import.MigrationConflict):
            clerk_import.import_users(db, provider, apply=True, sleep=lambda _: None)
        assert db.get(User, "legacy").clerk_user_id is None


def test_malformed_argon_hash_is_blocked_in_preflight():
    with SessionLocal() as db:
        db.add(
            User(
                name="A",
                email="a@example.com",
                password_hash="$argon2id$v=19$m=bad$bad$bad",
            )
        )
        db.commit()
        assert clerk_import.import_users(db, None, apply=False)["blocked"] == 1


def test_cutover_dry_run_preserves_sessions_and_apply_keeps_source_credentials():
    from datetime import timedelta
    from galvanise.models import Session as AuthSession, now
    from galvanise import clerk_cutover

    with SessionLocal() as db:
        user = User(name="A", email="a@example.com")
        db.add(user)
        db.flush()
        db.add_all(
            [
                AuthSession(
                    user_id=user.id,
                    token_hash="synthetic-hash",
                    expires_at=now() + timedelta(days=1),
                ),
                Account(
                    user_id=user.id,
                    github_id="1",
                    token_ciphertext=encrypt("synthetic-source"),
                ),
            ]
        )
        db.commit()
        assert clerk_cutover.invalidate_legacy_sessions(db) == {
            "legacy_sessions": 1,
            "invalidated": 0,
        }
        assert db.scalar(select(AuthSession)) is not None
        assert clerk_cutover.invalidate_legacy_sessions(db, apply=True) == {
            "legacy_sessions": 1,
            "invalidated": 1,
        }
        assert db.scalar(select(AuthSession)) is None
        assert (
            decrypt(db.scalar(select(Account)).token_ciphertext) == "synthetic-source"
        )


def test_concurrent_first_requests_create_one_owner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    isolated = create_engine(
        f"sqlite:///{tmp_path / 'concurrent.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(isolated)
    barrier = Barrier(2)

    class ConcurrentSession(Session):
        def commit(self):
            if not self.info.get("first_commit"):
                self.info["first_commit"] = True
                barrier.wait(timeout=10)
            super().commit()

    provider = Provider()
    provider.rows["user_new"] = remote()

    def open_workspace():
        with ConcurrentSession(isolated) as db:
            return clerk_identity.resolve_user(db, "user_new", provider).id

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(open_workspace)
            second = pool.submit(open_workspace)
            owners = [first.result(timeout=15), second.result(timeout=15)]
        assert owners[0] == owners[1]
        with Session(isolated) as db:
            assert len(db.scalars(select(User)).all()) == 1
        assert provider.get("user_new").external_id == owners[0]
    finally:
        isolated.dispose()


def test_verified_profile_changes_sync_without_changing_owner_uuid():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "updated@example.com", "legacy")
    provider.rows["user_old"].first_name = "Updated"
    with SessionLocal() as db:
        db.add(
            User(
                id="legacy",
                clerk_user_id="user_old",
                name="Original",
                email="original@example.com",
            )
        )
        db.commit()
        user = clerk_identity.resolve_user(db, "user_old", provider)
        assert (
            user.id == "legacy"
            and user.email == "updated@example.com"
            and user.name == "Updated"
        )


def test_profile_email_conflict_preserves_both_owners_and_mapping():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "other@example.com", "legacy")
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id="legacy",
                    clerk_user_id="user_old",
                    name="Original",
                    email="original@example.com",
                ),
                User(id="other", name="Other", email="other@example.com"),
            ]
        )
        db.commit()
        with pytest.raises(HTTPException) as e:
            clerk_identity.resolve_user(db, "user_old", provider)
        assert e.value.status_code == 409
        assert db.get(User, "legacy").email == "original@example.com"
        assert db.get(User, "legacy").clerk_user_id == "user_old"
