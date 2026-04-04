import uuid
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.postgres import Base


class RoleType(str, enum.Enum):
    lead = "lead"
    supporting = "supporting"
    recurring = "recurring"
    narrator = "narrator"
    villain = "villain"


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_type: Mapped[RoleType] = mapped_column(Enum(RoleType), nullable=False)
    visual_references: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    lora_model_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_profile_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    personality_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    backstory: Mapped[str | None] = mapped_column(Text, nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    appearance_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    instagram_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    engagement_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    castings: Mapped[list["CharacterCasting"]] = relationship("CharacterCasting", back_populates="character", cascade="all, delete-orphan")


class CastingRole(str, enum.Enum):
    lead = "lead"
    supporting = "supporting"
    recurring = "recurring"
    guest = "guest"
    cameo = "cameo"


class CastingStatus(str, enum.Enum):
    active = "active"
    written_out = "written_out"
    killed_off = "killed_off"
    recurring = "recurring"


class CharacterCasting(Base):
    __tablename__ = "character_castings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    character_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[CastingRole] = mapped_column(Enum(CastingRole), nullable=False)
    appearance_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    character_arc_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[CastingStatus] = mapped_column(Enum(CastingStatus), default=CastingStatus.active, nullable=False)

    character: Mapped["Character"] = relationship("Character", back_populates="castings")
    project: Mapped["Project"] = relationship("Project", back_populates="character_castings")
