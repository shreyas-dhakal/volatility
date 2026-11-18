from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from galvanise.agents.design_chat import command
from galvanise.database import Base, engine
from galvanise.main import app
from test_intelligence_api import FakeStream, create


def test_only_explicit_design_commands_authorize_mutations():
    assert command("Please design this system.") == "analyze_design"
    assert command("Plan project") == "plan_project"
    assert command("Correction: every site uses one tariff") == "revise_design"
    assert command("What if we change the design to use one tariff?") is None
    assert command("All sites will use one tariff") is None


def test_chat_reads_published_revision_without_mutation_tools(monkeypatch):
    from galvanise.design_engine import service
    from galvanise.routes import intelligence

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    revision = {"id": "v1", "snapshot": {"components": [
        {"id": "pricing", "responsibility": "Determine the charge under the tariff."}
    ]}}
    monkeypatch.setattr(service, "current_revision", lambda *args: revision)
    frames = FakeStream([
        SimpleNamespace(type="response.output_text.delta", delta="Pricing determines the charge."),
        SimpleNamespace(type="response.completed", response=SimpleNamespace(id="r1")),
    ])
    provider = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(return_value=frames)), close=AsyncMock()
    )
    monkeypatch.setattr(intelligence, "configured_client", lambda: provider)
    with TestClient(app) as c:
        pid = create(c)
        base = f"/api/projects/{pid}/conversations"
        conversation = c.get(base).json()[0]["id"]
        response = c.post(f"{base}/{conversation}/chat", json={"content": "Who determines the charge?"})
        assert response.status_code == 200 and "Pricing determines the charge" in response.text
        arguments = provider.responses.create.call_args.kwargs
        assert arguments["tools"] == []
        assert any("under the tariff" in msg["content"] for msg in arguments["input"])
