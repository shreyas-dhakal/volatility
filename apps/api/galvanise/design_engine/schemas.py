"""Structured model responses and the persisted design revision."""

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Texts = Annotated[list[Text], Field(min_length=1)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(Model):
    chunk_id: Text
    excerpt: Text = Field(
        description="Contiguous verbatim text copied from the supplied chunk, including original punctuation."
    )


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
    actor_id: Text = Field(description="ID from the supplied actors collection.")
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


class BoundaryExplanation(Model):
    owner_id: Text
    approach: Text
    established: Text = Field(
        description="What the cited passages establish, including limits on inference."
    )
    uncertainty: Text | None
    rationale: Text
    reconsider_when: Text
    hypothetical_alternative: Text | None
    evidence: list[Citation]


class ExplanationEdit(BoundaryExplanation):
    volatility_id: Text


class DecisionAnswer(Model):
    base_revision_id: Text
    question_id: Text
    question: Text
    evidence: Citation


class PublishedDecision(Volatility):
    explanation: BoundaryExplanation | None = None
    answers: list[DecisionAnswer] = Field(default_factory=list)


class Component(Entity):
    name: Text
    role: Literal[
        "manager", "engine", "resource_access", "resource", "client", "utility"
    ]
    responsibility: Text
    owns: list[Text] = Field(
        description="IDs from volatilities only, each assigned to exactly one primary component. Return [] when this component consumes a decision or owns no variability."
    )
    rationale: Text
    rationale_ids: list[Text] = Field(default_factory=list)
    use_case_ids: list[Text]
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
    caller_id: Text = Field(
        description="Component calling a different component. Never emit a dependency for a local step."
    )
    callee_id: Text = Field(
        description="The component owning the operation. Must differ from caller_id."
    )
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
    path: Text = Field(
        description="Use main for the normal flow, or copy one exception string verbatim from the referenced use case."
    )


class Walkthrough(Entity):
    use_case_id: Text
    steps: Annotated[list[Step], Field(min_length=1)]
    outcome: Text


class ComponentImpact(Model):
    component_id: Text
    reason: Text


class ChangeProbe(Entity):
    volatility_id: Text
    change: Text
    predicted_owner_ids: list[Text]
    predicted_edit_ids: list[Text]
    leaks: list[ComponentImpact]
    consumers: list[ComponentImpact] = Field(
        default_factory=list,
        description="Components that consume the outcome unchanged, with the contract detail that protects each.",
    )

    @model_validator(mode="after")
    def predictions_only(self):
        # Numerical policy changes (e.g. "cap the fee at $20") are valid.
        # Reject performance claims stated as measured results in predictive fields.
        statistics = re.compile(
            r"\b(?:measured|achieved|recorded|demonstrated|benchmarks? (?:show|showed))"
            r"[^.!?]{0,70}(?:\d+(?:\.\d+)?\s*%|\b(?:improvement|speedup|savings)\b)"
            r"|\b(?:improved|reduced|saved|decreased)\b[^.!?]{0,50}\bby\s+\d+(?:\.\d+)?\s*%",
            re.IGNORECASE,
        )
        if any(
            statistics.search(text)
            for text in [
                self.change,
                *(impact.reason for impact in [*self.leaks, *self.consumers]),
            ]
        ):
            raise ValueError(
                "Change probes contain predictions only. Put observed measurements in cited implementation findings."
            )
        return self


class Question(Entity):
    question: Text
    alternatives: list[Text] | None
    target_ids: Texts
    decision_impact: Text


class Finding(Entity):
    code: Text = Field(
        description="Use the exact code 'revision' for a review edit, 'ownership_gap' for an unassigned decision, or 'coverage_gap' for an untraced use case."
    )
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


class Edit(Model):
    retire: list[Retirement] = Field(default_factory=list)


class UseCaseEdit(UseCases, Edit):
    pass


class DecisionEdit(Decisions, Edit):
    pass


class BoundaryEdit(Boundaries, Edit):
    explanations: list[ExplanationEdit]


class TraceEdit(Traces, Edit):
    pass


class Review(Boundaries, Traces):
    explanations: list[ExplanationEdit]
    questions: Annotated[list[Question], Field(max_length=3)]
    retire: list[Retirement]


class Snapshot(Inventory, UseCases, Decisions, Boundaries, Traces):
    volatilities: list[PublishedDecision]
    analysis_type: Literal["design_analysis"] = "design_analysis"
    manifest: list[dict[str, Any]]
