"""Bounded structured output contracts for the independently reviewed design stages."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Ref = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Texts = Annotated[list[Text], Field(max_length=100)]
Refs = Annotated[list[Ref], Field(max_length=100)]
Links = Annotated[list[Ref], Field(min_length=1, max_length=100)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class UseCaseInput(Strict):
    title: Title
    description: str = Field(default='', max_length=6000)
    actor: str = Field(default='', max_length=2000)
    trigger: str = Field(default='', max_length=2000)
    preconditions: Texts = Field(default_factory=list)
    steps: Annotated[list[Text], Field(min_length=1, max_length=100)]
    outcome: Text
    variations: Texts = Field(default_factory=list)
    evidence_ids: Refs = Field(default_factory=list)


class Proposal(Strict):
    title: Title
    description: Text
    evidence_ids: Refs


class Reasoned(Proposal):
    uncertainty: Text
    open_questions: Texts


class CoreCase(Reasoned):
    use_case_ids: Links
    rationale: Text
    unresolved_use_case_ids: Refs


class Volatility(Reasoned):
    core_use_case_ids: Links
    axis: Literal['over_time', 'across_customer', 'both']
    what_changes: Text
    why_plausible: Text
    stable_aspects: Annotated[list[Text], Field(min_length=1, max_length=100)]
    examples: Annotated[list[Text], Field(min_length=1, max_length=100)]


class Component(Reasoned):
    component_role: Literal['client', 'manager', 'engine', 'resource_access', 'resource', 'utility']
    volatility_ids: Links
    responsibility: Text
    hidden_change: Text
    stable_contract: Text
    excluded_responsibilities: Texts
    dependencies: Refs


class Collaboration(Strict):
    core_use_case_id: Ref
    component_ids: Links
    steps: Annotated[list[Text], Field(min_length=1, max_length=100)]


class Scenario(Strict):
    title: Title
    volatility_id: Ref
    changed_component_ids: Links
    unchanged_component_ids: Refs
    rationale: Text


class Validation(Proposal):
    collaborations: Annotated[list[Collaboration], Field(min_length=1, max_length=100)]
    scenarios: Annotated[list[Scenario], Field(min_length=1, max_length=100)]
    assumptions: Texts


class CoreResult(Strict):
    records: Annotated[list[CoreCase], Field(min_length=1, max_length=30)]


class VolatilityResult(Strict):
    records: Annotated[list[Volatility], Field(min_length=1, max_length=30)]


class DecompositionResult(Strict):
    records: Annotated[list[Component], Field(min_length=1, max_length=30)]


class ValidationResult(Strict):
    records: Annotated[list[Validation], Field(min_length=1, max_length=10)]


class GenerateInput(Strict):
    stage: Literal['core', 'volatility', 'decomposition', 'validation']
