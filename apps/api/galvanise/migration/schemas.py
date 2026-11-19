from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Value(Data):
    name: str = Field(min_length=1, max_length=100)
    json_value: str = Field(max_length=6000)


class Seed(Data):
    fixture: str = Field(
        min_length=1, max_length=120, description="Logical fixture name"
    )
    values: list[Value] = Field(max_length=30)


class Step(Data):
    input: str = Field(
        min_length=1,
        max_length=120,
        description="Logical entry point name, never a URL or command",
    )
    values: list[Value] = Field(max_length=30)


class Observation(Data):
    kind: Literal["database", "http", "messages", "jobs"]
    target: str = Field(
        max_length=200, description="Logical table, destination, queue or worker"
    )
    fields: list[str] = Field(max_length=30)


class Scenario(Data):
    name: str = Field(min_length=1, max_length=120)
    category: Literal["normal", "reject", "retry_repeat", "boundary"]
    seed: list[Seed] = Field(max_length=30)
    steps: list[Step] = Field(min_length=1, max_length=8)
    observe: list[Observation] = Field(max_length=30)
    evidence_ids: list[str] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_values(self):
        from pydantic import TypeAdapter

        adapter = TypeAdapter(JsonValue)
        for entry in [*self.seed, *self.steps]:
            names = [v.name for v in entry.values]
            if len(set(names)) != len(names):
                raise ValueError("Input and fixture field names must be unique")
            for value in entry.values:
                adapter.validate_json(value.json_value)
        return self


class Suite(Data):
    scenarios: list[Scenario] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def unique_names(self):
        if len({x.name for x in self.scenarios}) != len(self.scenarios):
            raise ValueError("Scenario names must be unique")
        return self


class Selection(Data):
    query: str = Field(max_length=160)
    selected: list[str] = Field(min_length=1, max_length=50)


class Rule(Data):
    scenario: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=400)
    kind: Literal["id", "timestamp"]
    reason: str = Field(min_length=8, max_length=1000)


class Mapping(Data):
    legacy: str = Field(min_length=1, max_length=400)
    replacement: str = Field(min_length=1, max_length=400)
    reason: str = Field(min_length=8, max_length=1000)


class Approval(Data):
    capture_id: str
    rules: list[Rule] = Field(default_factory=list, max_length=50)


class IntentionalChange(Data):
    scenario: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, max_length=400)
    reason: str = Field(min_length=8, max_length=1000)


class Replacement(Data):
    target: str = Field(min_length=1, max_length=100)
    conventions: str = Field(default="", max_length=6000)
    mappings: list[Mapping] = Field(default_factory=list, max_length=100)
    intentional_changes: list[IntentionalChange] = Field(
        default_factory=list, max_length=50
    )


class Enqueue(Data):
    action: Literal[
        "generate", "baseline", "compare", "generate_patch", "repair", "draft_pr"
    ]
    request_id: str = Field(min_length=1, max_length=120)
    replacement: Replacement | None = None
    prior_job_id: str | None = None
    scenario: str | None = Field(default=None, max_length=120)
    repair: str = Field(default="", max_length=3000)


class AcceptPatch(Data):
    job_id: str
    reason: str = Field(min_length=8, max_length=2000)
