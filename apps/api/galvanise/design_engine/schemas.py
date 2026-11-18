"""Structured model responses and the persisted design revision."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Texts = Annotated[list[Text], Field(min_length=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(Model):
    chunk_id: Text
    excerpt: Text


class Entity(Model):
    id: Text
    evidence: list[Citation]


class Actor(Entity):
    name: Text
    kind: Literal["actor", "external_system", "resource"]
    description: Text


class Observation(Entity):
    title: Text
    description: Text
    kind: Literal[
        "implementation", "business_decision", "workflow", "conflict", "missing_context"
    ]
    evidence: Annotated[list[Citation], Field(min_length=1)]


class UseCase(Entity):
    name: Text
    actor_id: Text
    trigger: Text
    outcome: Text
    steps: Texts
    exceptions: list[Text]
    basis: Literal["observed", "stated_requirement", "inferred"]


class Alternative(Model):
    description: Text
    hypothetical: bool


class Volatility(Entity):
    decision: Text
    driver: Text
    alternatives: list[Alternative]
    status: Literal["observed", "user_confirmed", "hypothesis", "disputed"]
    use_case_ids: Texts


class Component(Entity):
    name: Text
    role: Literal[
        "manager", "engine", "resource_access", "resource", "client", "utility"
    ]
    responsibility: Text
    owns: list[Text]
    rationale: Text
    use_case_ids: Texts
    provisional: bool


class Operation(Model):
    id: Text
    name: Text
    inputs: list[Text]
    outputs: Texts
    failures: list[Text]


class Contract(Entity):
    name: Text
    owner_id: Text
    hides: Text
    operations: Annotated[list[Operation], Field(min_length=1)]


class Dependency(Entity):
    caller_id: Text
    callee_id: Text
    operation_id: Text
    reason: Text


class Step(Model):
    caller_id: Text
    callee_id: Text
    operation_id: Text | None
    dependency_id: Text | None
    coverage_gap: Text | None
    description: Text
    outcome: Text
    path: Text  # "main" or the exact use-case exception.


class Walkthrough(Entity):
    use_case_id: Text
    steps: Annotated[list[Step], Field(min_length=1)]
    outcome: Text


class Leak(Model):
    component_id: Text
    reason: Text


class ChangeProbe(Entity):
    volatility_id: Text
    change: Text
    predicted_owner_ids: list[Text]
    predicted_edit_ids: list[Text]
    leaks: list[Leak]


class Question(Entity):
    question: Text
    alternatives: list[Text] | None
    target_ids: Texts
    decision_impact: Text


class Finding(Entity):
    code: Text
    severity: Literal["info", "warning", "error"]
    message: Text
    target_ids: list[Text]


class Inventory(Model):
    actors: list[Actor]
    implementation_findings: list[Observation]


class UseCases(Model):
    use_cases: list[UseCase]


class Decisions(Model):
    volatilities: list[Volatility]
    questions: Annotated[list[Question], Field(max_length=3)]


class Boundaries(Model):
    components: list[Component]
    contracts: list[Contract]
    dependencies: list[Dependency]
    findings: list[Finding]


class Traces(Model):
    walkthroughs: list[Walkthrough]
    change_probes: list[ChangeProbe]
    findings: list[Finding]


class Retirement(Model):
    id: Text
    reason: Text


class Review(Boundaries, Traces):
    questions: Annotated[list[Question], Field(max_length=3)]
    retire: list[Retirement]


class Snapshot(Inventory, UseCases, Decisions, Boundaries, Traces):
    manifest: list[dict[str, Any]]
