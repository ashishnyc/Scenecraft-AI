/**
 * E2E-style test: open inbox → review pitches → approve one → task created
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PitchInbox from '../components/PitchInbox';
import type { Pitch } from '../api/pitches';
import type { Task } from '../api/tasks';

// ── mocks ────────────────────────────────────────────────────────────────────

vi.mock('../api/pitches', () => ({
  fetchPitches: vi.fn(),
  approvePitch: vi.fn(),
  rejectPitch: vi.fn(),
  updatePitchNotes: vi.fn(),
}));

vi.mock('../context/WorkspaceContext', () => ({
  useWorkspace: () => ({ currentWorkspace: { id: 'ws-1', name: 'Test WS' } }),
}));

import { fetchPitches, approvePitch, rejectPitch } from '../api/pitches';

// ── helpers ──────────────────────────────────────────────────────────────────

const mockPitch = (overrides: Partial<Pitch> = {}): Pitch => ({
  id: 'pitch-1',
  workspace_id: 'ws-1',
  title: 'How AI Is Changing Horror Content',
  concept_summary:
    'An in-depth look at how creators are using artificial intelligence to generate haunted house tour videos, with analysis of viral trends and audience psychology.',
  target_audience_hook: 'Horror fans who love behind-the-scenes tech breakdowns.',
  appeal_score: 8.2,
  source_topics: ['AI', 'horror'],
  originality_score: 0.78,
  similar_videos: null,
  notes: null,
  status: 'pending',
  created_at: new Date().toISOString(),
  ...overrides,
});

const mockTask = (): Task => ({
  id: 'task-99',
  project_id: 'proj-1',
  title: 'How AI Is Changing Horror Content',
  status: 'idea',
  concept_brief: 'An in-depth look…',
  creator_notes: null,
  script: null,
  final_video_url: null,
  youtube_video_id: null,
  total_cost_usd: null,
});

function renderInbox(onClose = vi.fn()) {
  return render(
    <MemoryRouter>
      <PitchInbox onClose={onClose} />
    </MemoryRouter>,
  );
}

// ── tests ────────────────────────────────────────────────────────────────────

describe('PitchInbox', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows empty state when no pitches', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([]);
    renderInbox();
    await waitFor(() =>
      expect(screen.getByText(/no pitches waiting for review/i)).toBeInTheDocument(),
    );
  });

  it('renders pitch cards with title and badges', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([mockPitch()]);
    renderInbox();

    await waitFor(() =>
      expect(screen.getByText('How AI Is Changing Horror Content')).toBeInTheDocument(),
    );
    // Originality badge
    expect(screen.getByText(/78% orig\./i)).toBeInTheDocument();
    // Appeal badge
    expect(screen.getByText(/★ 8.2/i)).toBeInTheDocument();
  });

  it('shows low originality badge for low-originality pitch', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([
      mockPitch({ originality_score: 0.08, status: 'low_originality' }),
    ]);
    renderInbox();
    await waitFor(() => expect(screen.getByText(/low orig\./i)).toBeInTheDocument());
  });

  it('approves a pitch and removes it from the list', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([mockPitch()]);
    vi.mocked(approvePitch).mockResolvedValue(mockTask());
    renderInbox();

    await waitFor(() =>
      expect(screen.getByText('How AI Is Changing Horror Content')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole('button', { name: /approve/i }));

    await waitFor(() =>
      expect(screen.queryByText('How AI Is Changing Horror Content')).not.toBeInTheDocument(),
    );
    expect(approvePitch).toHaveBeenCalledWith('ws-1', 'pitch-1');

    // Success toast
    await waitFor(() =>
      expect(screen.getByText(/approved — task created/i)).toBeInTheDocument(),
    );
  });

  it('rejects a pitch and removes it from the list', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([mockPitch()]);
    vi.mocked(rejectPitch).mockResolvedValue(mockPitch({ status: 'rejected' }));
    renderInbox();

    await waitFor(() =>
      expect(screen.getByText('How AI Is Changing Horror Content')).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole('button', { name: /reject/i }));

    await waitFor(() =>
      expect(screen.queryByText('How AI Is Changing Horror Content')).not.toBeInTheDocument(),
    );
    expect(rejectPitch).toHaveBeenCalledWith('ws-1', 'pitch-1');
  });

  it('closes drawer when overlay is clicked', async () => {
    vi.mocked(fetchPitches).mockResolvedValue([]);
    const onClose = vi.fn();
    renderInbox(onClose);
    await waitFor(() => screen.getByRole('dialog'));

    // Click the overlay (first sibling div)
    const overlay = document.querySelector('[class*="overlay"]') as HTMLElement;
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalled();
  });
});
