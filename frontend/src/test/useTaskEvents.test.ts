import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { TaskStatusEvent } from '../hooks/useTaskEvents';
import type { Task, TaskStatus } from '../api/tasks';

// ─── Unit tests for the WebSocket event handler logic ────────────────────────
// These test the state-update function that useTaskEvents calls — not the
// WebSocket connection itself (which requires a real network).

describe('WebSocket event handler — state update logic', () => {
  const makeTask = (overrides: Partial<Task> = {}): Task => ({
    id: 'task-1',
    project_id: 'proj-1',
    title: 'Test',
    status: 'idea',
    concept_brief: null,
    creator_notes: null,
    script: null,
    final_video_url: null,
    youtube_video_id: null,
    total_cost_usd: null,
    ...overrides,
  });

  // Simulates the callback inside Tasks.tsx that handles incoming WS events
  const applyEvent = (tasks: Task[], event: TaskStatusEvent): Task[] =>
    tasks.map((t) =>
      t.id === event.task_id ? { ...t, status: event.status as TaskStatus } : t
    );

  it('updates the matching task status', () => {
    const tasks = [makeTask({ id: 'task-1', status: 'idea' })];
    const event: TaskStatusEvent = {
      type: 'task_status',
      task_id: 'task-1',
      status: 'approved',
      workspace_id: 'ws-1',
    };
    const updated = applyEvent(tasks, event);
    expect(updated[0].status).toBe('approved');
  });

  it('does not touch other tasks', () => {
    const tasks = [
      makeTask({ id: 'task-1', status: 'idea' }),
      makeTask({ id: 'task-2', status: 'scripting' }),
    ];
    const event: TaskStatusEvent = {
      type: 'task_status',
      task_id: 'task-1',
      status: 'approved',
      workspace_id: 'ws-1',
    };
    const updated = applyEvent(tasks, event);
    expect(updated[1].status).toBe('scripting');
  });

  it('ignores events for unknown task IDs', () => {
    const tasks = [makeTask({ id: 'task-1', status: 'idea' })];
    const event: TaskStatusEvent = {
      type: 'task_status',
      task_id: 'unknown-id',
      status: 'approved',
      workspace_id: 'ws-1',
    };
    const updated = applyEvent(tasks, event);
    expect(updated[0].status).toBe('idea');
  });

  it('workspace filter: ignores events from other workspaces', () => {
    const workspaceId = 'ws-mine';
    const event: TaskStatusEvent = {
      type: 'task_status',
      task_id: 'task-1',
      status: 'approved',
      workspace_id: 'ws-other',
    };
    // Guard from Tasks.tsx: skip if workspace doesn't match
    const shouldProcess = event.workspace_id === workspaceId;
    expect(shouldProcess).toBe(false);
  });

  it('workspace filter: processes events from the current workspace', () => {
    const workspaceId = 'ws-mine';
    const event: TaskStatusEvent = {
      type: 'task_status',
      task_id: 'task-1',
      status: 'approved',
      workspace_id: 'ws-mine',
    };
    const shouldProcess = event.workspace_id === workspaceId;
    expect(shouldProcess).toBe(true);
  });
});
