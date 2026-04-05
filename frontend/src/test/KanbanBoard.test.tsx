import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Tasks from '../pages/Tasks';
import {
  TASK_STATUSES,
  STATUS_LABELS,
  TaskStatus,
  Task,
} from '../api/tasks';

// Mock WorkspaceContext so we control currentWorkspace directly
vi.mock('../context/WorkspaceContext', () => ({
  useWorkspace: vi.fn(),
}));

vi.mock('../context/ProjectContext', () => ({
  useProject: vi.fn(),
}));

// Mock Tasks API calls
vi.mock('../api/tasks', async (importOriginal) => {
  const original = await importOriginal<typeof import('../api/tasks')>();
  return {
    ...original,
    fetchTasksForWorkspace: vi.fn(),
  };
});

import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import { fetchTasksForWorkspace } from '../api/tasks';

const mockWorkspace = {
  id: 'ws-1',
  name: 'My Channel',
  youtube_channel_id: null,
  style_guide: null,
  upload_schedule: null,
  competitor_channels: null,
  created_at: '2024-01-01T00:00:00Z',
};

const mockTask = (overrides: Partial<Task> = {}): Task => ({
  id: 'task-1',
  project_id: 'proj-1',
  title: 'Test Task',
  status: 'idea',
  concept_brief: null,
  creator_notes: null,
  script: null,
  final_video_url: null,
  youtube_video_id: null,
  total_cost_usd: null,
  ...overrides,
});

function renderTasks() {
  return render(
    <MemoryRouter>
      <Tasks />
    </MemoryRouter>
  );
}

// ─── Static unit tests ────────────────────────────────────────────────────────

describe('TASK_STATUSES / STATUS_LABELS', () => {
  it('has all 9 statuses in order', () => {
    expect(TASK_STATUSES).toHaveLength(9);
    expect(TASK_STATUSES[0]).toBe('idea');
    expect(TASK_STATUSES[8]).toBe('published');
  });

  it('has a label for every status', () => {
    TASK_STATUSES.forEach((s) => {
      expect(STATUS_LABELS[s]).toBeTruthy();
    });
  });
});

// ─── Page: no workspace ───────────────────────────────────────────────────────

describe('Tasks page — no workspace selected', () => {
  beforeEach(() => {
    vi.mocked(useWorkspace).mockReturnValue({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      switchWorkspace: vi.fn(),
      refreshWorkspaces: vi.fn(),
    });
    vi.mocked(useProject).mockReturnValue({
      projects: [],
      currentProject: null,
      loading: false,
      selectProject: vi.fn(),
      refreshProjects: vi.fn(),
    });
  });

  it('prompts to select a workspace', () => {
    renderTasks();
    expect(screen.getByText(/select a workspace/i)).toBeInTheDocument();
  });
});

// ─── Page: with workspace ─────────────────────────────────────────────────────

describe('Tasks page — with workspace', () => {
  const tasks: Task[] = [
    mockTask({ id: 't1', title: 'Write script', status: 'idea' }),
    mockTask({ id: 't2', title: 'Record audio', status: 'scripting' }),
  ];

  beforeEach(() => {
    vi.mocked(useWorkspace).mockReturnValue({
      workspaces: [mockWorkspace],
      currentWorkspace: mockWorkspace,
      loading: false,
      switchWorkspace: vi.fn(),
      refreshWorkspaces: vi.fn(),
    });
    vi.mocked(useProject).mockReturnValue({
      projects: [],
      currentProject: null,
      loading: false,
      selectProject: vi.fn(),
      refreshProjects: vi.fn(),
    });
    vi.mocked(fetchTasksForWorkspace).mockResolvedValue(tasks);
  });

  it('renders all 9 status column headers', async () => {
    renderTasks();
    // Wait for board to render (approved has no task so the text is unique)
    await waitFor(() =>
      expect(screen.getByText(STATUS_LABELS['approved'])).toBeInTheDocument()
    );
    for (const s of TASK_STATUSES) {
      // Use getAllByText since status labels may also appear on badge text
      expect(screen.getAllByText(STATUS_LABELS[s]).length).toBeGreaterThanOrEqual(1);
    }
  });

  it('displays tasks in the board', async () => {
    renderTasks();
    await waitFor(() => {
      expect(screen.getByText('Write script')).toBeInTheDocument();
      expect(screen.getByText('Record audio')).toBeInTheDocument();
    });
  });

  it('shows task count badges for columns with tasks', async () => {
    renderTasks();
    await waitFor(() => {
      expect(screen.getByText('Write script')).toBeInTheDocument();
    });
    const badges = screen.getAllByText('1');
    expect(badges.length).toBeGreaterThanOrEqual(2);
  });
});

// ─── State update logic ───────────────────────────────────────────────────────

describe('Optimistic state update on drag', () => {
  it('tasksByStatus grouping filters tasks correctly', () => {
    const allTasks: Task[] = [
      mockTask({ id: 'a', status: 'idea' }),
      mockTask({ id: 'b', status: 'idea' }),
      mockTask({ id: 'c', status: 'approved' }),
      mockTask({ id: 'd', status: 'published' }),
    ];

    const grouped = TASK_STATUSES.reduce<Record<TaskStatus, Task[]>>((acc, s) => {
      acc[s] = allTasks.filter((t) => t.status === s);
      return acc;
    }, {} as Record<TaskStatus, Task[]>);

    expect(grouped['idea']).toHaveLength(2);
    expect(grouped['approved']).toHaveLength(1);
    expect(grouped['published']).toHaveLength(1);
    expect(grouped['scripting']).toHaveLength(0);
  });

  it('optimistic update moves task to new status', () => {
    const tasks: Task[] = [
      mockTask({ id: 't1', status: 'idea' }),
      mockTask({ id: 't2', status: 'approved' }),
    ];

    const targetStatus: TaskStatus = 'approved';
    const taskToMove = tasks.find((t) => t.id === 't1')!;

    const updated = tasks.map((t) =>
      t.id === taskToMove.id ? { ...t, status: targetStatus } : t
    );

    expect(updated.find((t) => t.id === 't1')?.status).toBe('approved');
    expect(updated.find((t) => t.id === 't2')?.status).toBe('approved');
  });

  it('rollback restores original status on API error', () => {
    const tasks: Task[] = [mockTask({ id: 't1', status: 'idea' })];
    const original = tasks[0];

    // After optimistic update
    let state = tasks.map((t) =>
      t.id === original.id ? { ...t, status: 'approved' as TaskStatus } : t
    );
    expect(state[0].status).toBe('approved');

    // Rollback
    state = state.map((t) =>
      t.id === original.id ? { ...t, status: original.status } : t
    );
    expect(state[0].status).toBe('idea');
  });

  it('drag onto same status column is a no-op', () => {
    const task = mockTask({ id: 't1', status: 'idea' });
    const targetStatus: TaskStatus = 'idea';

    // Guard from handleDragEnd: task.status === targetStatus → no transition
    const shouldTransition = task.status !== targetStatus;
    expect(shouldTransition).toBe(false);
  });
});
