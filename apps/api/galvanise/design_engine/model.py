import json

from galvanise.agents.client import configured_client
from galvanise.config import settings

from .prompts import RULES, STAGES


async def call_model(stage, context):
    schema, instruction = STAGES[stage]
    async with configured_client() as client:
        response = await client.responses.parse(
            model=settings.design_model or settings.openai_model,
            instructions=RULES + "\n" + instruction,
            input=json.dumps(context, ensure_ascii=False),
            text_format=schema,
        )
    if response.status != "completed" or response.output_parsed is None:
        raise ValueError(f"The {stage} model response was incomplete or refused.")
    return response.output_parsed.model_dump()
