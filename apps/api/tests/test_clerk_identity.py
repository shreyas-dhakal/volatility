"""Clerk identity mapping, owner preservation and profile synchronization."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="sqlite://",
    SOURCE_TOKEN_ENCRYPTION_KEY="isolated-test-source-encryption-key",
    AUTO_CREATE_TABLES="true",
)
from types import SimpleNamespace as NS

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from galvanise import clerk_identity, clerk_reconcile
from galvanise.database import Base, SessionLocal, engine
from galvanise.models import Account, Project, User
from galvanise.security import decrypt, encrypt


class Provider:
    def __init__(self):
        self.rows = {}

    def get(self, subject):
        return self.rows[subject]

    def find(self, external_id):
        return [row for row in self.rows.values() if row.external_id == external_id]

    def update(self, subject, external_id):
        self.rows[subject].external_id = external_id


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


def test_mapped_subject_keeps_local_owner_and_source_credentials():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "owner@example.com", "owner-id")
    with SessionLocal() as db:
        user = User(
            id="owner-id",
            clerk_user_id="user_old",
            name="Owner",
            email="owner@example.com",
        )
        db.add(user)
        db.flush()
        db.add(Project(user_id=user.id, name="Private"))
        db.add(
            Account(
                user_id=user.id,
                github_id="123",
                token_ciphertext=encrypt("synthetic-source-token"),
            )
        )
        db.commit()
        resolved = clerk_identity.resolve_user(db, "user_old", provider)
        assert resolved.id == "owner-id"
        assert db.scalar(select(Project)).user_id == "owner-id"
        assert (
            decrypt(db.scalar(select(Account)).token_ciphertext)
            == "synthetic-source-token"
        )


def test_new_clerk_subject_is_provisioned_once():
    provider = Provider()
    provider.rows["user_new"] = remote()
    with SessionLocal() as db:
        user = clerk_identity.resolve_user(db, "user_new", provider)
        assert user.clerk_user_id == "user_new"
        assert provider.get("user_new").external_id == user.id
        assert clerk_identity.resolve_user(db, "user_new", provider).id == user.id
        assert len(db.scalars(select(User)).all()) == 1


def test_existing_clerk_account_can_open_a_fresh_workspace():
    provider = Provider()
    provider.rows["user_new"] = remote(external_id="existing-owner")
    with SessionLocal() as db:
        user = clerk_identity.resolve_user(db, "user_new", provider)
        assert user.id == "existing-owner"
        assert clerk_identity.resolve_user(db, "user_new", provider).id == user.id


def test_external_id_cannot_claim_an_existing_owner():
    provider = Provider()
    provider.rows["user_new"] = remote(external_id="existing-owner")
    with SessionLocal() as db:
        db.add(User(id="existing-owner", clerk_user_id="another-subject",
                    name="Owner", email="other@example.com"))
        db.commit()
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert error.value.status_code == 409
        assert db.get(User, "existing-owner").clerk_user_id == "another-subject"


def test_new_subject_cannot_claim_an_existing_email():
    provider = Provider()
    provider.rows["user_new"] = remote(email="owner@example.com")
    with SessionLocal() as db:
        db.add(User(id="owner-id", name="Owner", email="owner@example.com"))
        db.commit()
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert error.value.status_code == 409
        assert db.get(User, "owner-id").clerk_user_id is None


def test_unverified_new_user_cannot_be_provisioned():
    provider = Provider()
    provider.rows["user_new"] = remote(verified=False)
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert error.value.status_code == 403
        assert not db.scalars(select(User)).all()


def test_failed_external_id_sync_denies_access_then_reconciles_same_user():
    provider = Provider()
    provider.rows["user_new"] = remote()
    original_update = provider.update
    provider.update = lambda *_: (_ for _ in ()).throw(TimeoutError())
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert error.value.status_code == 503
        original_update("user_new", db.scalar(select(User)).id)
        assert clerk_identity.resolve_user(db, "user_new", provider).id


def test_banned_user_is_denied_even_with_mapping():
    provider = Provider()
    provider.rows["user_new"] = remote()
    provider.rows["user_new"].banned = True
    with SessionLocal() as db:
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_new", provider)
        assert error.value.status_code == 401


def test_profile_changes_sync_without_changing_owner_id():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "updated@example.com", "owner-id")
    provider.rows["user_old"].first_name = "Updated"
    with SessionLocal() as db:
        db.add(
            User(
                id="owner-id",
                clerk_user_id="user_old",
                name="Original",
                email="original@example.com",
            )
        )
        db.commit()
        user = clerk_identity.resolve_user(db, "user_old", provider)
        assert user.id == "owner-id"
        assert user.email == "updated@example.com"
        assert user.name == "Updated"


def test_profile_email_conflict_preserves_existing_mappings():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "other@example.com", "owner-id")
    with SessionLocal() as db:
        db.add_all(
            [
                User(
                    id="owner-id",
                    clerk_user_id="user_old",
                    name="Owner",
                    email="owner@example.com",
                ),
                User(id="other-id", name="Other", email="other@example.com"),
            ]
        )
        db.commit()
        with pytest.raises(HTTPException) as error:
            clerk_identity.resolve_user(db, "user_old", provider)
        assert error.value.status_code == 409
        assert db.get(User, "owner-id").email == "owner@example.com"
        assert db.get(User, "owner-id").clerk_user_id == "user_old"


def test_reconciliation_checks_prelinked_clerk_accounts():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "owner@example.com", "owner-id")
    with SessionLocal() as db:
        db.add(
            User(
                id="owner-id",
                clerk_user_id="user_old",
                name="Owner",
                email="owner@example.com",
            )
        )
        db.commit()
        assert clerk_reconcile.reconcile_mapped_users(db, provider) == {
            "mapped": 1,
            "reconciled": 1,
        }


def test_reconciliation_rejects_a_mismatched_upstream_identity():
    provider = Provider()
    provider.rows["user_old"] = remote("user_old", "other@example.com", "owner-id")
    with SessionLocal() as db:
        db.add(
            User(
                id="owner-id",
                clerk_user_id="user_old",
                name="Owner",
                email="owner@example.com",
            )
        )
        db.commit()
        with pytest.raises(clerk_reconcile.ReconciliationConflict):
            clerk_reconcile.reconcile_mapped_users(db, provider)
        assert db.get(User, "owner-id").email == "owner@example.com"
