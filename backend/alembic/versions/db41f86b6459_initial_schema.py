"""initial_schema

Revision ID: db41f86b6459
Revises: 
Create Date: 2026-04-04 23:31:54.357881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'db41f86b6459'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- workspaces ---
    op.create_table(
        "workspaces",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("youtube_channel_id", sa.String(255), nullable=True),
        sa.Column("youtube_oauth_token", sa.Text, nullable=True),
        sa.Column("style_guide", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("upload_schedule", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("competitor_channels", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # --- characters (account-level, no FK to workspace) ---
    op.create_table(
        "characters",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role_type", sa.Enum("lead", "supporting", "recurring", "narrator", "villain", name="roletype"), nullable=False),
        sa.Column("visual_references", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("lora_model_url", sa.Text, nullable=True),
        sa.Column("voice_profile_id", sa.String(255), nullable=True),
        sa.Column("personality_prompt", sa.Text, nullable=True),
        sa.Column("backstory", sa.Text, nullable=True),
        sa.Column("age", sa.Integer, nullable=True),
        sa.Column("appearance_state", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("instagram_config", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("engagement_stats", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_characters_account_id", "characters", ["account_id"])

    # --- projects ---
    op.create_table(
        "projects",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.Enum("serialised", "anthology", name="projecttype"), nullable=False),
        sa.Column("story_bible", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("status", sa.Enum("active", "completed", "paused", name="projectstatus"), nullable=False, server_default="active"),
        sa.Column("episode_count", sa.Integer, nullable=True),
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    # --- character_castings ---
    op.create_table(
        "character_castings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("character_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("characters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum("lead", "supporting", "recurring", "guest", "cameo", name="castingrole"), nullable=False),
        sa.Column("appearance_override", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("character_arc_notes", sa.Text, nullable=True),
        sa.Column("first_episode", sa.Integer, nullable=True),
        sa.Column("status", sa.Enum("active", "written_out", "killed_off", "recurring", name="castingstatus"), nullable=False, server_default="active"),
    )
    op.create_index("ix_castings_character_id", "character_castings", ["character_id"])
    op.create_index("ix_castings_project_id", "character_castings", ["project_id"])

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.Enum(
            "idea", "approved", "scripting", "audio_preview", "script_review",
            "producing", "final_review", "scheduled", "published",
            name="taskstatus"
        ), nullable=False, server_default="idea"),
        sa.Column("concept_brief", sa.Text, nullable=True),
        sa.Column("creator_notes", sa.Text, nullable=True),
        sa.Column("script", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("final_video_url", sa.Text, nullable=True),
        sa.Column("youtube_video_id", sa.String(255), nullable=True),
        sa.Column("performance_metrics", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("total_cost_usd", sa.Numeric(10, 4), nullable=True),
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    # --- subtasks ---
    op.create_table(
        "subtasks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.Enum(
            "ideation", "script", "audio_preview", "review", "scene_plan",
            "visual_gen", "audio_gen", "assembly", "final_review", "metadata", "publish",
            name="subtasktype"
        ), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "done", "failed", "waiting_review", name="subtaskstatus"), nullable=False, server_default="queued"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.Column("output_artifacts", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("error_log", sa.Text, nullable=True),
    )
    op.create_index("ix_subtasks_task_id", "subtasks", ["task_id"])

    # --- review_actions ---
    op.create_table(
        "review_actions",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subtask_id", sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey("subtasks.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.Enum("approve", "reject", "request_changes", name="reviewactiontype"), nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_review_actions_task_id", "review_actions", ["task_id"])


def downgrade() -> None:
    op.drop_table("review_actions")
    op.drop_table("subtasks")
    op.drop_table("tasks")
    op.drop_table("character_castings")
    op.drop_table("projects")
    op.drop_table("characters")
    op.drop_table("workspaces")

    # Drop custom enum types
    for enum_name in ["reviewactiontype", "subtaskstatus", "subtasktype", "taskstatus",
                      "castingstatus", "castingrole", "projectstatus", "projecttype", "roletype"]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
