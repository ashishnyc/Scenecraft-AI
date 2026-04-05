import { NavLink } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
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

  return (
    <aside className={styles.sidebar} aria-label="Main navigation">
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoMark}>SC</span>
        <span className={styles.logoText}>Scenecraft</span>
      </div>

      {/* Workspace switcher placeholder */}
      <div className={styles.workspaceSwitcher}>
        <span className={styles.workspaceLabel}>Workspace</span>
        <button className={styles.workspaceButton}>My Workspace ▾</button>
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
