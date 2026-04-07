"""Per-workspace AI configuration with per-feature model overrides."""
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres import Base


class WorkspaceAIConfig(Base):
    __tablename__ = "workspace_ai_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # Default provider: "ollama" | "openai" | "anthropic"
    provider: Mapped[str] = mapped_column(String(50), nullable=False, default="ollama")
    model: Mapped[str] = mapped_column(String(255), nullable=False, default="kimi-k2.5:cloud")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Encrypted API key (None for Ollama which needs no key)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-feature overrides stored as JSONB.
    # Shape: { "feature_name": { "provider": "...", "model": "...", "base_url": "...", "api_key_encrypted": "..." } }
    feature_overrides: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped["Workspace"] = relationship("Workspace", back_populates="ai_config")
