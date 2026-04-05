import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../context/AuthContext';
import { Sidebar } from '../components/Sidebar';

function renderSidebar() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <Sidebar />
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
  expect(screen.getByText(/My Workspace/)).toBeInTheDocument();
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
