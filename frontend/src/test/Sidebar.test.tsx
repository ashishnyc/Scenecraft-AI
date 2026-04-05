import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi, beforeEach } from 'vitest';
import { AuthProvider } from '../context/AuthContext';
import { WorkspaceProvider } from '../context/WorkspaceContext';
import { ProjectProvider } from '../context/ProjectContext';
import { Sidebar } from '../components/Sidebar';
import { apiClient } from '../api/client';

vi.mock('../api/client', () => ({
  apiClient: { get: vi.fn() },
}));

beforeEach(() => {
  vi.mocked(apiClient.get).mockResolvedValue({ data: [] });
});

function renderSidebar() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <WorkspaceProvider>
          <ProjectProvider>
            <Sidebar />
          </ProjectProvider>
        </WorkspaceProvider>
      </AuthProvider>
    </MemoryRouter>
  );
}

test('renders all navigation items', () => {
  renderSidebar();
  expect(screen.getByText('Dashboard')).toBeInTheDocument();
  expect(screen.getByText('Tasks')).toBeInTheDocument();
  expect(screen.getByText('Script Review')).toBeInTheDocument();
  expect(screen.getByText('Talent Roster')).toBeInTheDocument();
  expect(screen.getByText('Analytics')).toBeInTheDocument();
  expect(screen.getByText('Settings')).toBeInTheDocument();
});

test('renders workspace switcher', () => {
  renderSidebar();
  expect(screen.getByText(/No workspace|Channel/)).toBeInTheDocument();
});

test('renders sign out button', () => {
  renderSidebar();
  expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument();
});

test('nav items are links', () => {
  renderSidebar();
  const nav = screen.getByRole('navigation');
  const links = nav.querySelectorAll('a');
  expect(links.length).toBe(6);
});

test('renders projects section', () => {
  renderSidebar();
  expect(screen.getByText('Projects')).toBeInTheDocument();
});
