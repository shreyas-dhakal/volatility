"""Resumable backend-only import. The database mapping is the durable checkpoint.

Dry-run is the default and performs no Clerk calls. Apply requires an explicit
operator confirmation and development instance configuration; never dump hashes.
"""

import argparse
import json
import time

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
from sqlalchemy import select

from galvanise.clerk_identity import primary_email, provider
from galvanise.models import Account, User


class MigrationConflict(Exception):
    pass


def import_payload(user, has_github):
    payload = {
        "external_id": user.id,
        "email_address": [user.email.strip().lower()],
        "email_address_identification_status": ["reserved"],
        "first_name": user.name,
    }
    if user.password_hash:
        variant = (
            user.password_hash.split("$")[1]
            if user.password_hash.startswith("$")
            else ""
        )
        if (
            variant not in ("argon2id", "argon2i")
            or len(user.password_hash.split("$")) != 6
        ):
            raise MigrationConflict("Unsupported password hash")
        try:
            extract_parameters(user.password_hash)
        except (InvalidHashError, ValueError):
            raise MigrationConflict("Malformed password hash") from None
        payload.update(password_digest=user.password_hash, password_hasher=variant)
    elif has_github:
        payload["skip_password_requirement"] = True
    else:
        raise MigrationConflict("Account has no supported sign-in method")
    return payload


def reconcile(db, user, remote):
    email = primary_email(remote)
    if (
        remote.external_id != user.id
        or not email
        or email.email_address.strip().lower() != user.email.strip().lower()
        or (user.clerk_user_id and user.clerk_user_id != remote.id)
        or db.scalar(
            select(User.id).where(User.clerk_user_id == remote.id, User.id != user.id)
        )
    ):
        raise MigrationConflict("Identity conflict; operator reconciliation required")
    user.clerk_user_id = remote.id
    db.commit()


def import_users(db, identity_provider=None, *, apply=False, sleep=time.sleep):
    users = db.scalars(select(User).order_by(User.id)).all()
    payloads = []
    emails = set()
    blocked = 0
    for user in users:
        try:
            normalized = user.email.strip().lower()
            if normalized in emails or "@" not in normalized:
                raise MigrationConflict("Email conflict")
            emails.add(normalized)
            payloads.append(
                (
                    user,
                    import_payload(
                        user,
                        db.scalar(select(Account.id).where(Account.user_id == user.id))
                        is not None,
                    ),
                )
            )
        except MigrationConflict:
            blocked += 1
    result = {
        "total": len(users),
        "ready": len(payloads),
        "blocked": blocked,
        "migrated": 0,
    }
    if not apply or blocked:
        return result
    upstream = identity_provider or provider()
    for user, payload in payloads:
        for attempt in range(4):
            try:
                existing = upstream.find(user.id)
                if len(existing) > 1:
                    raise MigrationConflict("Duplicate external identity")
                if existing:
                    remote = existing[0]
                elif user.clerk_user_id:
                    raise MigrationConflict("Mapped identity missing upstream")
                else:
                    remote = upstream.create(**payload)
                reconcile(db, user, remote)
                result["migrated"] += 1
                break
            except MigrationConflict:
                raise
            except Exception as error:  # noqa: BLE001 -- reconcile ambiguous SDK/transport failures
                db.rollback()
                status = getattr(error, "status_code", None)
                if status and status not in (408, 429) and status < 500:
                    raise MigrationConflict(
                        "Clerk rejected import; reconcile before retry"
                    ) from None
                if attempt == 3:
                    raise MigrationConflict(
                        "Import interrupted; rerun to reconcile checkpoint"
                    ) from None
                retry_after = getattr(
                    getattr(error, "raw_response", None), "headers", {}
                ).get("retry-after", "")
                try:
                    delay = max(2**attempt, float(retry_after))
                except (ValueError, TypeError):
                    delay = 2**attempt
                sleep(min(delay, 30))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-development-import", action="store_true")
    args = parser.parse_args()
    from galvanise.config import settings
    from galvanise.database import SessionLocal

    if args.apply and (
        not args.confirm_development_import
        or settings.app_env != "development"
        or not settings.clerk_secret_key.startswith("sk_test_")
    ):
        parser.error("Apply requires explicit confirmation and a development instance")
    with SessionLocal() as db:
        try:
            result = import_users(db, apply=args.apply)
        except MigrationConflict as error:
            print(json.dumps({"error": str(error)}))
            raise SystemExit(1) from None
    print(json.dumps(result))
    if result["blocked"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
