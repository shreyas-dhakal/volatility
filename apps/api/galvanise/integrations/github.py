import httpx
from clerk_backend_api.models import ClerkBaseError
from fastapi import HTTPException

from galvanise.clerk_identity import provider


def account_token(user):
    account = user.github_account
    if account is None:
        raise HTTPException(400, "Connect GitHub through Clerk first")
    try:
        tokens = provider().github_tokens(user.clerk_user_id)
    except ClerkBaseError as error:
        try:
            codes = {item["code"] for item in error.raw_response.json()["errors"]}
        except (ValueError, KeyError, TypeError):
            codes = set()
        if "oauth_shared_credentials_stored_token_not_retrievable" in codes:
            # Shared development credentials allow identity linking but no token export.
            return None
        raise HTTPException(
            502, "Reconnect GitHub in your Clerk profile and retry"
        ) from None
    except Exception:
        raise HTTPException(503, "Clerk is unavailable. Try again shortly.") from None
    for credential in tokens:
        if credential.external_account_id == account.id and credential.token:
            return credential.token
    return None


def api(token, path, params=None):
    try:
        r = httpx.get(
            "https://api.github.com" + path,
            headers={
                **({"Authorization": "Bearer " + token} if token else {}),
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            params=params,
            timeout=25,
        )
        if r.status_code == 429 or (
            r.status_code == 403 and r.headers.get("x-ratelimit-remaining") == "0"
        ):
            raise HTTPException(
                429,
                "GitHub’s read limit was reached. Try again after the limit resets.",
            )
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            502, "GitHub request failed; reconnect your account and retry"
        )


def repositories(user):
    token = account_token(user)
    path = "/user/repos"
    filters = {"visibility": "public"}
    if token is None:
        # Resolve by immutable provider ID so a renamed or reused login stays safe.
        github_id = user.github_account.provider_user_id
        if not github_id.isdecimal():
            raise HTTPException(502, "Clerk returned an invalid GitHub account")
        login = api(None, "/user/" + github_id)["login"]
        path = f"/users/{login}/repos"
        filters = {"type": "owner"}
    result = []
    for page in range(1, 11):
        batch = api(
            token,
            path,
            {"per_page": 100, "page": page, "sort": "updated", **filters},
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
