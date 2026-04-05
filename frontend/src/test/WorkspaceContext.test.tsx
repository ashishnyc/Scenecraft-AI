import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { vi, beforeEach } from 'vitest';
import { WorkspaceProvider, useWorkspace } from '../context/WorkspaceContext';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn(), put: vi.fn() },
}));

const mockWorkspaces = [
  { id: 'ws-1', name: 'Channel One', youtube_channel_id: null, style_guide: null, upload_schedule: null, competitor_channels: null, created_at: '' },
  { id: 'ws-2', name: 'Channel Two', youtube_channel_id: null, style_guide: null, upload_schedule: null, competitor_channels: null, created_at: '' },
];

beforeEach(() => {
  localStorage.clear();
  vi.mocked(apiClient.get).mockResolvedValue({ data: mockWorkspaces });
});

function TestConsumer() {
  const { workspaces, currentWorkspace, switchWorkspace } = useWorkspace();
  return (
    <div>
      <span data-testid="current">{currentWorkspace?.name ?? 'none'}</span>
      <span data-testid="count">{workspaces.length}</span>
      <button onClick={() => switchWorkspace('ws-2')}>Switch to Two</button>
    </div>
  );
}

function renderWithProviders() {
  return render(
    <MemoryRouter>
      <WorkspaceProvider>
        <TestConsumer />
      </WorkspaceProvider>
    </MemoryRouter>
  );
}

test('loads workspaces and selects first by default', async () => {
  renderWithProviders();
  expect(await screen.findByTestId('current')).toHaveTextContent('Channel One');
  expect(screen.getByTestId('count')).toHaveTextContent('2');
});

test('switchWorkspace updates current workspace', async () => {
  renderWithProviders();
  await screen.findByTestId('current');
  await act(async () => userEvent.click(screen.getByText('Switch to Two')));
  expect(screen.getByTestId('current')).toHaveTextContent('Channel Two');
});

test('persists selected workspace in localStorage', async () => {
  renderWithProviders();
  await screen.findByTestId('current');
  await act(async () => userEvent.click(screen.getByText('Switch to Two')));
  expect(localStorage.getItem('sc_workspace_id')).toBe('ws-2');
});

test('restores workspace from localStorage on mount', async () => {
  localStorage.setItem('sc_workspace_id', 'ws-2');
  renderWithProviders();
  expect(await screen.findByTestId('current')).toHaveTextContent('Channel Two');
});
