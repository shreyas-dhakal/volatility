"""Reconcile pre-linked Clerk subjects with stable local account ownership."""

import argparse
import json

from sqlalchemy import select

from galvanise.clerk_identity import primary_email, provider
from galvanise.models import User


class ReconciliationConflict(Exception):
    pass


def reconcile(db, user, remote):
    email = primary_email(remote)
    if (
        remote.external_id != user.id
        or not email
        or not email.verification
        or email.verification.status != "verified"
        or email.email_address.strip().lower() != user.email.strip().lower()
        or (user.clerk_user_id and user.clerk_user_id != remote.id)
        or db.scalar(
            select(User.id).where(User.clerk_user_id == remote.id, User.id != user.id)
        )
    ):
        raise ReconciliationConflict(
            "Identity conflict; operator reconciliation required"
        )
    user.clerk_user_id = remote.id
    db.commit()


def reconcile_mapped_users(db, identity_provider=None):
    users = db.scalars(
        select(User).where(User.clerk_user_id.is_not(None)).order_by(User.id)
    ).all()
    upstream = identity_provider or provider()
    for user in users:
        matches = upstream.find(user.id)
        if len(matches) != 1:
            raise ReconciliationConflict(
                "Mapped identity missing or duplicated upstream"
            )
        reconcile(db, user, matches[0])
    return {"mapped": len(users), "reconciled": len(users)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from galvanise.database import SessionLocal

    with SessionLocal() as db:
        try:
            result = (
                reconcile_mapped_users(db)
                if args.apply
                else {
                    "mapped": len(
                        db.scalars(
                            select(User.id).where(User.clerk_user_id.is_not(None))
                        ).all()
                    )
                }
            )
        except ReconciliationConflict as error:
            print(json.dumps({"error": str(error)}))
            raise SystemExit(1) from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
