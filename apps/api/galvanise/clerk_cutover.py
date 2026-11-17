"""Development-only legacy session cleanup (dry-run by default).

First stop legacy sign-in writes and deploy AUTH_MODE=clerk on both tiers.
This command does not switch deployment modes or delete source credentials.
"""

import argparse
import json

from sqlalchemy import delete, func, select

from galvanise.models import Session as AuthSession


def invalidate_legacy_sessions(db, *, apply=False):
    count = db.scalar(select(func.count()).select_from(AuthSession))
    if apply:
        db.execute(delete(AuthSession))
        db.commit()
    return {"legacy_sessions": count, "invalidated": count if apply else 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-development-cutover", action="store_true")
    args = parser.parse_args()
    from galvanise.config import settings
    from galvanise.database import SessionLocal

    if args.apply and (
        not args.confirm_development_cutover
        or settings.app_env != "development"
        or settings.auth_mode != "clerk"
    ):
        parser.error(
            "Apply requires explicit development cutover confirmation and Clerk mode"
        )
    with SessionLocal() as db:
        print(json.dumps(invalidate_legacy_sessions(db, apply=args.apply)))


if __name__ == "__main__":
    main()
