from fastapi import APIRouter, Depends

from galvanise.dependencies import get_current_user
from galvanise.integrations.github import project_id_for_repo, repositories
from galvanise.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "github_connected": user.github_account is not None,
    }


@router.get("/github/repos")
def repos(user: User = Depends(get_current_user)):
    return [
        {**repo, "project_id": project_id_for_repo(user, repo["id"])}
        for repo in repositories(user)
    ]
