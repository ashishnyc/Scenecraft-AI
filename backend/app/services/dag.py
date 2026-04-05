"""Topological sort (Kahn's algorithm) for subtask dependency ordering."""
from collections import deque


class CyclicDependencyError(ValueError):
    pass


def topological_sort(subtasks: list) -> list:
    """Return subtasks in dependency order (dependencies first).

    Each subtask must have an `id` (UUID) and `depends_on` (list of UUID strings or None).

    Raises CyclicDependencyError if a cycle is detected.
    """
    id_to_subtask = {str(s.id): s for s in subtasks}
    in_degree: dict[str, int] = {str(s.id): 0 for s in subtasks}
    dependents: dict[str, list[str]] = {str(s.id): [] for s in subtasks}

    for subtask in subtasks:
        for dep_id in (subtask.depends_on or []):
            if dep_id in id_to_subtask:
                in_degree[str(subtask.id)] += 1
                dependents[dep_id].append(str(subtask.id))

    queue = deque(sid for sid, deg in in_degree.items() if deg == 0)
    result = []

    while queue:
        sid = queue.popleft()
        result.append(id_to_subtask[sid])
        for dependent_id in dependents[sid]:
            in_degree[dependent_id] -= 1
            if in_degree[dependent_id] == 0:
                queue.append(dependent_id)

    if len(result) != len(subtasks):
        raise CyclicDependencyError("Cyclic dependency detected in subtasks")

    return result


def check_dependencies_met(subtask, all_subtasks: list) -> list[str]:
    """Return list of unmet dependency IDs (deps not in 'done' status)."""
    id_to_subtask = {str(s.id): s for s in all_subtasks}
    unmet = []
    for dep_id in (subtask.depends_on or []):
        dep = id_to_subtask.get(dep_id)
        if dep is None or dep.status.value != "done":
            unmet.append(dep_id)
    return unmet
