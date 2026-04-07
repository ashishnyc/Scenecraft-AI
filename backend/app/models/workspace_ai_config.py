"""Per-workspace AI configuration — maps features to named model configs."""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class WorkspaceAIConfig(Base):
    __tablename__ = "workspace_ai_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # The default named config used when no feature override is set (nullable = fall back to .env)
    default_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspace_ai_model_configs.id", ondelete="SET NULL"), nullable=True
    )

    # Per-feature overrides: { "outline_generation": "<config_uuid>", ... }
    feature_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="ai_config")
    default_config: Mapped["WorkspaceAIModelConfig | None"] = relationship(
        "WorkspaceAIModelConfig", foreign_keys=[default_config_id]
    )
