import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { to: '/',          label: 'Dashboard',     icon: '⬛' },
  { to: '/tasks',     label: 'Tasks',         icon: '📋' },
  { to: '/scripts',   label: 'Script Review', icon: '📝' },
  { to: '/talent',    label: 'Talent Roster', icon: '🎭' },
  { to: '/analytics', label: 'Analytics',     icon: '📊' },
  { to: '/settings',  label: 'Settings',      icon: '⚙️' },
];

export function Sidebar() {
  const { logout } = useAuth();
  const { workspaces, currentWorkspace, switchWorkspace } = useWorkspace();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  return (
    <aside className={styles.sidebar} aria-label="Main navigation">
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoMark}>SC</span>
        <span className={styles.logoText}>Scenecraft</span>
      </div>

      {/* Workspace switcher */}
      <div className={styles.workspaceSwitcher}>
        <span className={styles.workspaceLabel}>Workspace</span>
        <div className={styles.dropdownWrapper}>
          <button
            className={styles.workspaceButton}
            onClick={() => setDropdownOpen((o) => !o)}
            aria-haspopup="listbox"
            aria-expanded={dropdownOpen}
          >
            {currentWorkspace?.name ?? 'No workspace'} ▾
          </button>
          {dropdownOpen && workspaces.length > 0 && (
            <ul className={styles.dropdown} role="listbox">
              {workspaces.map((ws) => (
                <li
                  key={ws.id}
                  role="option"
                  aria-selected={ws.id === currentWorkspace?.id}
                  className={`${styles.dropdownItem} ${ws.id === currentWorkspace?.id ? styles.dropdownItemActive : ''}`}
                  onClick={() => { switchWorkspace(ws.id); setDropdownOpen(false); }}
                >
                  {ws.name}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav className={styles.nav}>
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
            }
          >
            <span className={styles.navIcon}>{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Logout */}
      <button className={styles.logoutButton} onClick={logout}>
        Sign out
      </button>
    </aside>
  );
}
