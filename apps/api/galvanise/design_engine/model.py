import json

from galvanise.agents.client import configured_client
from galvanise.config import settings

from .prompts import RULES, STAGES


def reference_aliases(context):
    """Short handles are private to one provider call. Stored IDs remain authoritative."""
    aliases = {c["id"]: f"source_{i}" for i, c in enumerate(context["chunks"], 1)}
    for collection, records in context.get("prior", {}).items():
        for i, record in enumerate(records, 1):
            aliases[record["id"]] = f"{collection}_{i}"
            for j, operation in enumerate(record.get("operations", []), 1):
                aliases[operation["id"]] = f"op_{i}_{j}"
    for i, hint in enumerate(context.get("prior_ids", []), 1):
        aliases.setdefault(hint["id"], f"prior_{i}")
        for j, operation_id in enumerate(hint.get("operation_ids", []), 1):
            aliases.setdefault(operation_id, f"prior_op_{i}_{j}")
    return aliases


def translate(value, aliases, field=None):
    if isinstance(value, dict):
        return {key: translate(item, aliases, key) for key, item in value.items()}
    if isinstance(value, list):
        return [translate(item, aliases, field) for item in value]
    if not isinstance(value, str) or not field:
        return value
    if field in ("id", "owns") or field.endswith(("_id", "_ids")):
        return aliases.get(value, value)
    return value


async def call_model(stage, context):
    schema, instruction = STAGES[stage]
    selected_model = settings.design_model or settings.openai_model
    aliases = reference_aliases(context)
    inputs = translate(context, aliases)
    if "repair" in inputs:
        diagnostics = inputs["repair"]["diagnostics"]
        for identity, handle in aliases.items():
            diagnostics = diagnostics.replace(identity, handle)
        inputs["repair"]["diagnostics"] = diagnostics
    async with configured_client(model=selected_model) as client:
        response = await client.responses.parse(
            model=selected_model,
            instructions=RULES
            + "\n"
            + instruction
            + (
                "\nCopy reference handles exactly. New IDs start with new_. "
                "Copy short, contiguous supporting phrases directly from the source text. "
                "Use separate citations for nonadjacent phrases."
            ),
            input=json.dumps(inputs, ensure_ascii=False),
            timeout=300,
            text_format=schema,
        )
    if response.status != "completed" or response.output_parsed is None:
        raise ValueError(f"The {stage} model response was incomplete or refused.")
    persistent = {handle: identity for identity, handle in aliases.items()}
    return translate(response.output_parsed.model_dump(), persistent)
