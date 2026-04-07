"""Task lifecycle state machine.

Valid transitions (linear pipeline):
  brainstorm → idea_review → outline → writing_review →
  generate_script → script_review → generate_clips →
  assemble_clips → video_review → prepare_metadata → publish → closed

Guards:
  → idea_review   requires concept_brief to be set
"""
from app.models.task import TaskStatus

# Map each status to the set of statuses it can transition TO
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.brainstorm:      {TaskStatus.idea_review},
    TaskStatus.idea_review:     {TaskStatus.outline},
    TaskStatus.outline:         {TaskStatus.writing_review},
    TaskStatus.writing_review:  {TaskStatus.generate_script},
    TaskStatus.generate_script: {TaskStatus.script_review},
    TaskStatus.script_review:   {TaskStatus.generate_clips},
    TaskStatus.generate_clips:  {TaskStatus.assemble_clips},
    TaskStatus.assemble_clips:  {TaskStatus.video_review},
    TaskStatus.video_review:    {TaskStatus.prepare_metadata},
    TaskStatus.prepare_metadata:{TaskStatus.publish},
    TaskStatus.publish:         {TaskStatus.closed},
    TaskStatus.closed:          set(),
}


class InvalidTransitionError(ValueError):
    pass


class TransitionGuardError(ValueError):
    pass


def validate_transition(current: TaskStatus, target: TaskStatus, task) -> None:
    """Raise if the transition is not allowed or a guard fails.

    Args:
        current: current task status
        target:  requested new status
        task:    Task ORM instance (used for guard checks)
    """
    allowed = VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition from '{current}' to '{target}'. "
            f"Allowed next states: {[s.value for s in allowed] or 'none (terminal state)'}."
        )

    # Guard: brainstorm → idea_review requires concept_brief
    if current == TaskStatus.brainstorm and target == TaskStatus.idea_review:
        if not task.concept_brief:
            raise TransitionGuardError(
                "Cannot submit for review without a concept_brief. "
                "Set concept_brief before moving to review."
            )
