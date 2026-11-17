import httpx
from fastapi import HTTPException
from sqlalchemy import select

from galvanise.models import Account
from galvanise.security import decrypt


def account_token(db, user_id):
    account = db.scalar(select(Account).where(Account.user_id == user_id))
    if not account:
        raise HTTPException(400, "Connect GitHub first")
    return decrypt(account.token_ciphertext)


def api(token, path, params=None):
    try:
        r = httpx.get(
            "https://api.github.com" + path,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params=params,
            timeout=25,
        )
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502, "GitHub request failed; reconnect your account and retry"
        )


def repositories(token):
    result = []
    for page in range(1, 11):
        batch = api(
            token,
            "/user/repos",
            {"per_page": 100, "page": page, "sort": "updated", "visibility": "public"},
        )
        result.extend(
            {
                k: r.get(k)
                for k in ("id", "full_name", "description", "private", "default_branch")
            }
            for r in batch
            if not r.get("private")
        )
        if len(batch) < 100:
            break
    return result
