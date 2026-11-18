from datetime import datetime, timezone
from typing import ClassVar
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from galvanise.database import Base


def now():
    return datetime.now(timezone.utc)


def uid():
    return str(uuid4())


class Identity:
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Identity, Base):
    __tablename__ = "users"
    # Request-scoped Clerk profile data, never persisted.
    github_account = None
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    clerk_user_id: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )


class Account(Identity, Base):
    __tablename__ = "accounts"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    github_id: Mapped[str] = mapped_column(String, unique=True)
    token_ciphertext: Mapped[str] = mapped_column(Text)


class OAuthState(Identity, Base):
    __tablename__ = "oauth_states"
    state_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Project(Identity, Base):
    __tablename__ = "projects"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    system_type: Mapped[str] = mapped_column(String, default="existing")
    objective: Mapped[str] = mapped_column(Text, default="")


class ProjectOwned(Identity):
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )


class Conversation(ProjectOwned, Base):
    __tablename__ = "conversations"
    title: Mapped[str] = mapped_column(String, default="New conversation")


class Message(ProjectOwned, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ConnectedSource(ProjectOwned, Base):
    __tablename__ = "connected_sources"
    kind: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceDocument(ProjectOwned, Base):
    __tablename__ = "source_documents"
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("connected_sources.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String, default="text/plain")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class KnowledgeRecord(ProjectOwned, Base):
    __tablename__ = "knowledge_records"
    kind: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="pending")
    evidence_status: Mapped[str] = mapped_column(String, default="hypothesis")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    history: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )
    __mapper_args__ = {"polymorphic_on": kind, "polymorphic_identity": "record"}


class BusinessRequirement(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "requirement"}


class BusinessDecision(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "decision"}


class ChangeDriver(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "driver"}


class VolatilityHypothesis(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "volatility"}


class StakeholderQuestion(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "question"}


class StakeholderAnswer(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "answer"}


class ArchitectureCandidate(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "architecture"}


class ArchitectureBoundary(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "boundary"}


class EvidenceReference(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "evidence"}


class TraceabilityLink(KnowledgeRecord):
    __mapper_args__ = {"polymorphic_identity": "traceability"}


class TechnicalGraph(ProjectOwned, Base):
    __tablename__ = "technical_graphs"
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("connected_sources.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String)
    nodes_json: Mapped[list] = mapped_column(JSON, default=list)
    edges_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class IngestionJob(ProjectOwned, Base):
    __tablename__ = "ingestion_jobs"
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class UseCase(KnowledgeRecord):
    __mapper_args__: ClassVar[dict] = {"polymorphic_identity": "use_case"}


class CoreUseCase(KnowledgeRecord):
    __mapper_args__: ClassVar[dict] = {"polymorphic_identity": "core_use_case"}


class DesignValidation(KnowledgeRecord):
    __mapper_args__: ClassVar[dict] = {"polymorphic_identity": "design_validation"}


class DesignSource(ProjectOwned, Base):
    __tablename__ = "design_source"
    __table_args__ = (UniqueConstraint("project_id", "origin", "content_hash"),)
    # The origin distinguishes two files with identical text and different locators.
    origin: Mapped[str] = mapped_column(String)
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("source_documents.id", ondelete="SET NULL")
    )
    message_id: Mapped[str | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL")
    )
    content_hash: Mapped[str] = mapped_column(String)
    extraction_status: Mapped[str] = mapped_column(String)
    locator_json: Mapped[dict] = mapped_column(JSON)
    detail: Mapped[str] = mapped_column(Text, default="")


class DesignChunk(Identity, Base):
    __tablename__ = "design_chunk"
    __table_args__ = (UniqueConstraint("source_id", "ordinal"),)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("design_source.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    locator_json: Mapped[dict] = mapped_column(JSON)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)


class DesignRevision(ProjectOwned, Base):
    __tablename__ = "design_revision"
    parent_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_revision.id")
    )
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    diff_json: Mapped[dict] = mapped_column(JSON)
    source_ids: Mapped[list] = mapped_column(JSON)


class DesignHead(Base):
    __tablename__ = "design_head"
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    current_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_revision.id")
    )


class DesignRun(ProjectOwned, Base):
    __tablename__ = "design_run"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key"),)
    base_revision_id: Mapped[str | None] = mapped_column(
        ForeignKey("design_revision.id")
    )
    revision_id: Mapped[str | None] = mapped_column(ForeignKey("design_revision.id"))
    idempotency_key: Mapped[str] = mapped_column(String)
    operation: Mapped[str] = mapped_column(String)
    request_json: Mapped[dict] = mapped_column(JSON)
    source_ids: Mapped[list | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, index=True)
    stage: Mapped[str] = mapped_column(String)
    start_stage: Mapped[str] = mapped_column(String)
    checkpoint_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    diagnostics: Mapped[list] = mapped_column(JSON, default=list)
    claim_token: Mapped[str | None] = mapped_column(String)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now
    )


class DesignPlan(ProjectOwned, Base):
    __tablename__ = "design_plan"
    revision_id: Mapped[str] = mapped_column(ForeignKey("design_revision.id"))
    input_json: Mapped[dict] = mapped_column(JSON)
    result_json: Mapped[dict] = mapped_column(JSON)
