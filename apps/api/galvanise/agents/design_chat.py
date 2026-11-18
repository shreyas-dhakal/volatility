"""Route explicit design commands and ground conversational reads in one revision."""

import json
import re

from galvanise.models import Message


def command(content):
    text = content.strip().casefold().rstrip(".!?").strip()
    text = re.sub(r"^(?:(?:can|could|would) you |please )+", "", text)
    text = text.removesuffix(" for me").strip()
    if re.fullmatch(
        r"(?:design|redesign|analy[sz]e the design of) (?:this |the |my )?(?:system|project)",
        text,
    ):
        return "analyze_design"
    if re.fullmatch(
        r"(?:plan (?:this |the |my )?project|generate (?:the )?project execution options)",
        text,
    ):
        return "plan_project"
    if "?" not in content and re.match(
        r"^(?:correction\s*:|apply (?:this |the )?correction\b|(?:update|revise|correct|change) (?:the |this |my )?(?:design|architecture|assumption|contract)\b)",
        text,
    ):
        return "revise_design"
    return None


def requests_existing_workflow(content):
    """An explicit knowledge/graph command remains available after design publication."""
    return bool(
        re.match(
            r"^(?:please )?(?:create|record|save|extract|generate|map|trace|discover|evaluate) "
            r"(?:the |a |an )?(?:business |project |stakeholder |architecture |technical |change )?"
            r"(?:requirements?|decisions?|drivers?|questions?|hypotheses|candidates?|graphs?|scenarios?|answers?|dependencies|code)\b",
            content.strip(),
            re.IGNORECASE,
        )
    )


def grounding(snapshot, question, limit=60000):
    """Select whole records for large designs, keeping their IDs and provenance."""
    payload = json.dumps(snapshot, ensure_ascii=False)
    if len(payload) <= limit:
        return payload
    words = set(re.findall(r"\w{3,}", question.casefold()))
    records = []
    for kind, values in snapshot.items():
        for item in values if isinstance(values, list) else [values]:
            encoded = json.dumps(item, ensure_ascii=False)
            overlap = words.intersection(re.findall(r"\w{3,}", encoded.casefold()))
            records.append((len(overlap), kind, item, len(encoded)))
    selected = {}
    remaining = limit
    for _, kind, item, size in sorted(records, key=lambda row: -row[0]):
        if size + len(kind) + 10 <= remaining:
            selected.setdefault(kind, []).append(item)
            remaining -= size + len(kind) + 10
    return json.dumps(
        {"partial_revision": True, "records": selected}, ensure_ascii=False
    )


def perform(operation, db, project_id, user, conversation_id, content, revision):
    from galvanise.design_engine import service

    if operation != "analyze_design" and not revision:
        answer = "Design the system first so this operation has a published architecture to use."
        result = {}
    else:
        answer = None
    message = Message(
        project_id=project_id,
        conversation_id=conversation_id,
        role="user",
        content=content,
    )
    db.add(message)
    db.flush()
    if answer is None:
        if operation == "analyze_design":
            result = service.analyze_design(
                db,
                project_id,
                user,
                request_message_id=message.id,
                idempotency_key=message.id,
            )
            answer = (
                "System design queued. Open the design view to follow the analysis."
            )
        elif operation == "revise_design":
            result = service.revise_design(
                db,
                project_id,
                user,
                base_revision_id=revision["id"],
                correction_message_id=message.id,
                idempotency_key=message.id,
            )
            answer = "Correction queued. The design view will show the revision and its changes."
        else:
            result = service.plan_project(
                db, project_id, user, revision_id=revision["id"], planning_inputs={}
            )
            answer = "Open Project in the design view to review the activities and enter scheduling inputs."
    metadata = {"design_operation": operation, "result_id": result.get("id")}
    assistant = Message(
        project_id=project_id,
        conversation_id=conversation_id,
        role="assistant",
        content=answer,
        metadata_json=metadata,
    )
    db.add(assistant)
    db.commit()
    return answer, assistant.id, metadata
