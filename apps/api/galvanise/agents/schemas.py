from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Proposal(Strict):
    kind: Literal['requirement','decision','driver','volatility','question','answer','architecture','boundary','evidence','traceability']
    title: str = Field(min_length=1,max_length=300)
    description: str = Field(max_length=6000)
    evidence_ids: list[str]
    node_ids: list[str]
    change_driver: str
    affected_decisions: list[str]
    stable_decisions: list[str]
    time_horizon: str
    volatility_type: Literal['observed','anticipated','technical_instability','unspecified']
    stakeholder_role: str
    uncertainty: str
    open_questions: list[str]
    recommended_investigation: str


class Extraction(Strict):
    records: list[Proposal]


class Boundary(Strict):
    name: str
    responsibility: str
    boundary_type: Literal['module','interface','adapter','policy','configuration','service']
    change_drivers: list[str]
    stable_contract: str
    node_ids: list[str]
    included_responsibilities: list[str]
    excluded_responsibilities: list[str]
    evidence_ids: list[str]
    dependencies: list[str]
    benefits: list[str]
    tradeoffs: list[str]
    migration: list[str]
    open_questions: list[str]


class Candidate(Strict):
    name: str
    approach: Literal['conservative','volatility-aware']
    rationale: str
    boundaries: list[Boundary]
    assumptions: list[str]


class Candidates(Strict):
    candidates: list[Candidate]


class Mapping(Strict):
    node_id: str
    rationale: str
    evidence_ids: list[str]


class Mappings(Strict):
    links: list[Mapping]
