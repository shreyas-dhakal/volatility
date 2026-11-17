"""Owner-scoped, explicitly invoked design workflow."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from galvanise.agents.client import configured_client, structured
from galvanise.agents.design_schemas import GenerateInput, UseCaseInput
from galvanise.database import get_db
from galvanise.dependencies import get_current_user, require_project
from galvanise.models import User
from galvanise.services import design
from galvanise.services.knowledge import serialize
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/projects/{project_id}/design")
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("")
def overview(project_id: str, db: Database, user: CurrentUser):
    require_project(project_id, db, user)
    return design.view(db, project_id)


@router.post("/use-cases")
def use_case(project_id: str, body: UseCaseInput, db: Database, user: CurrentUser):
    require_project(project_id, db, user)
    try:
        return serialize(design.intake(db, project_id, body))
    except ValueError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error


@router.post("/generate")
async def generate(
    project_id: str, body: GenerateInput, db: Database, user: CurrentUser
):
    require_project(project_id, db, user)
    inputs = design.prerequisites(db, project_id, body.stage)
    context = design.context_for(db, project_id, inputs, body.stage)
    client = configured_client()
    try:
        result = await structured(
            client,
            design.RESULTS[body.stage],
            design.PROMPTS[body.stage]
            + " Use reviewed_usable inputs for stage links; core discovery alone may use pending original use cases. Preserve explicit uncertainty and evidence provenance.",
            context,
        )
        records = design.save_generated(
            db, project_id, body.stage, result, inputs, context["context_limits"]
        )
        return {"records": [serialize(r) for r in records]}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as error:
        db.rollback()
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        db.rollback()
        raise HTTPException(
            502,
            "AI design generation failed; no proposals were saved. Check server credentials/model availability and retry.",
        ) from error
    finally:
        await client.close()
