"""redesign pipeline stages to 5-stage workflow

Revision ID: j0k1l2m3n4o5
Revises: 1937f22abdba
Create Date: 2026-04-07

New statuses:
  Stage 1 (Idea):       brainstorm, idea_review
  Stage 2 (Writing):    outline, writing_review
  Stage 3 (Scripting):  generate_script, script_review
  Stage 4 (Video):      generate_clips, assemble_clips, video_review
  Stage 5 (Upload):     prepare_metadata, publish, closed

Old → new mapping:
  idea          → brainstorm
  approved      → idea_review
  scripting     → generate_script
  audio_preview → generate_script
  script_review → script_review
  producing     → generate_clips
  final_review  → video_review
  scheduled     → prepare_metadata
  published     → publish
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'j0k1l2m3n4o5'
down_revision: Union[str, Sequence[str], None] = '1937f22abdba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Convert status column to plain text so we can drop the old enum
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE TEXT")

    # 2. Drop the old enum type
    op.execute("DROP TYPE taskstatus")

    # 3. Map old values to new values
    op.execute("""
        UPDATE tasks SET status = CASE status
            WHEN 'idea'          THEN 'brainstorm'
            WHEN 'approved'      THEN 'idea_review'
            WHEN 'scripting'     THEN 'generate_script'
            WHEN 'audio_preview' THEN 'generate_script'
            WHEN 'script_review' THEN 'script_review'
            WHEN 'producing'     THEN 'generate_clips'
            WHEN 'final_review'  THEN 'video_review'
            WHEN 'scheduled'     THEN 'prepare_metadata'
            WHEN 'published'     THEN 'publish'
            ELSE 'brainstorm'
        END
    """)

    # 4. Create the new enum type
    op.execute("""
        CREATE TYPE taskstatus AS ENUM (
            'brainstorm', 'idea_review',
            'outline', 'writing_review',
            'generate_script', 'script_review',
            'generate_clips', 'assemble_clips', 'video_review',
            'prepare_metadata', 'publish', 'closed'
        )
    """)

    # 5. Cast column back to the new enum
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status TYPE taskstatus USING status::taskstatus"
    )

    # 6. Update the column default
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'brainstorm'::taskstatus")


def downgrade() -> None:
    # 1. Convert to text
    op.execute("ALTER TABLE tasks ALTER COLUMN status TYPE TEXT")

    # 2. Drop new enum
    op.execute("DROP TYPE taskstatus")

    # 3. Map new values back to old (best-effort)
    op.execute("""
        UPDATE tasks SET status = CASE status
            WHEN 'brainstorm'       THEN 'idea'
            WHEN 'idea_review'      THEN 'approved'
            WHEN 'outline'          THEN 'scripting'
            WHEN 'writing_review'   THEN 'scripting'
            WHEN 'generate_script'  THEN 'scripting'
            WHEN 'script_review'    THEN 'script_review'
            WHEN 'generate_clips'   THEN 'producing'
            WHEN 'assemble_clips'   THEN 'producing'
            WHEN 'video_review'     THEN 'final_review'
            WHEN 'prepare_metadata' THEN 'scheduled'
            WHEN 'publish'          THEN 'published'
            WHEN 'closed'           THEN 'published'
            ELSE 'idea'
        END
    """)

    # 4. Recreate old enum
    op.execute("""
        CREATE TYPE taskstatus AS ENUM (
            'idea', 'approved', 'scripting', 'audio_preview',
            'script_review', 'producing', 'final_review', 'scheduled', 'published'
        )
    """)

    # 5. Cast back
    op.execute(
        "ALTER TABLE tasks ALTER COLUMN status TYPE taskstatus USING status::taskstatus"
    )

    # 6. Restore old default
    op.execute("ALTER TABLE tasks ALTER COLUMN status SET DEFAULT 'idea'::taskstatus")
