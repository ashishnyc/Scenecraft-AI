"""Task lifecycle state machine.

Valid transitions:
  idea → approved → scripting → audio_preview → script_review
       → producing → final_review → scheduled → published

Guards:
  → approved   requires concept_brief to be set
"""
from app.models.task import TaskStatus

# Map each status to the set of statuses it can transition TO
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.idea:          {TaskStatus.approved},
    TaskStatus.approved:      {TaskStatus.scripting},
    TaskStatus.scripting:     {TaskStatus.audio_preview},
    TaskStatus.audio_preview: {TaskStatus.script_review},
    TaskStatus.script_review: {TaskStatus.producing},
    TaskStatus.producing:     {TaskStatus.final_review},
    TaskStatus.final_review:  {TaskStatus.scheduled},
    TaskStatus.scheduled:     {TaskStatus.published},
    TaskStatus.published:     set(),
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

    # Guard: idea → approved requires concept_brief
    if current == TaskStatus.idea and target == TaskStatus.approved:
        if not task.concept_brief:
            raise TransitionGuardError(
                "Cannot approve a task without a concept_brief. "
                "Set concept_brief before approving."
            )
