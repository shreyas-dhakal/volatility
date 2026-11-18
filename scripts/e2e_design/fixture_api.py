"""Uvicorn entry point for browser acceptance. Only the two model calls vary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from galvanise.design_engine import pipeline
from galvanise.main import app
from galvanise.routes import intelligence
from parking_model import CORRECTION_TEXT, ParkingModel

__all__ = ["app"]

pipeline.call_model = ParkingModel()


async def chat_response(*, tools, input, **kwargs):
    # Sending a plain statement takes the read-only path until the user applies it.
    assert tools == []
    assert input[-1]["content"] == CORRECTION_TEXT
    assert any("Tariff policy" in message["content"] for message in input[:-1])
    stream = MagicMock()
    stream.__aiter__.return_value = [
        SimpleNamespace(
            type="response.output_text.delta",
            delta="Apply this as a correction to revise the tariff.",
        ),
        SimpleNamespace(
            type="response.completed", response=SimpleNamespace(id="fixture-chat")
        ),
    ]
    return stream


def chat_provider():
    return SimpleNamespace(
        responses=SimpleNamespace(create=chat_response), close=AsyncMock()
    )


intelligence.configured_client = chat_provider
