import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import { NewProjectModal } from './NewProjectModal';
import { createProject } from '../api/projects';
import styles from './Sidebar.module.css';

// Workspace-level nav (always visible)
const WORKSPACE_NAV = [
  { to: '/',       label: 'Dashboard',     icon: '▦' },
  { to: '/talent', label: 'Talent Roster', icon: '◉' },
];

// Series pipeline nav (only when a series is selected)
const SERIES_NAV = [
  { to: '/tasks',        label: 'Videos',        icon: '▤' },
  { to: '/scripts',      label: 'Script Review', icon: '✎' },
  { to: '/video-review', label: 'Video Review',  icon: '▶' },
  { to: '/publish',      label: 'Publish',       icon: '↑' },
];

function initials(name: string) {
  return name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
}

export function Sidebar() {
  const { logout } = useAuth();
  const { currentWorkspace } = useWorkspace();
  const { projects, currentProject, selectProject, refreshProjects } = useProject();
  const navigate = useNavigate();

  const [seriesOpen, setSeriesOpen] = useState(false);
  const [showNewSeries, setShowNewSeries] = useState(false);

  const handleCreateSeries = async (data: Parameters<typeof createProject>[1]) => {
    if (!currentWorkspace) return;
    await createProject(currentWorkspace.id, data);
    await refreshProjects();
    setShowNewSeries(false);
  };

  const handleSelectSeries = (project: typeof projects[number]) => {
    selectProject(project);
    setSeriesOpen(false);
    navigate('/projects');
  };

  return (
    <aside className={styles.sidebar} aria-label="Main navigation">
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoMark}>SC</span>
        <span className={styles.logoText}>
          Scenecraft
          <span className={styles.logoSub}>AI Studio</span>
        </span>
      </div>

      {/* Series switcher */}
      <div className={styles.seriesSwitcher}>
        <div className={styles.switcherLabelRow}>
          <span className={styles.switcherLabel}>Series</span>
        </div>
        <div className={styles.dropdownWrapper}>
          <button
            className={styles.switcherButton}
            onClick={() => setSeriesOpen((o) => !o)}
            aria-haspopup="listbox"
            aria-expanded={seriesOpen}
          >
            {currentProject ? (
              <>
                <span className={styles.switcherDot} />
                <span className={styles.switcherName}>{currentProject.name}</span>
              </>
            ) : (
              <span className={styles.switcherPlaceholder}>Select a series</span>
            )}
          </button>

          {seriesOpen && (
            <ul className={styles.dropdown} role="listbox">
              {projects.map((p) => (
                <li
                  key={p.id}
                  role="option"
                  aria-selected={p.id === currentProject?.id}
                  className={`${styles.dropdownItem} ${p.id === currentProject?.id ? styles.dropdownItemActive : ''}`}
                  onClick={() => handleSelectSeries(p)}
                >
                  <span className={styles.dropdownDot} />
                  {p.name}
                </li>
              ))}
              {projects.length > 0 && <hr className={styles.dropdownDivider} />}
              <li
                className={styles.dropdownNewItem}
                onClick={() => { setSeriesOpen(false); setShowNewSeries(true); }}
              >
                + New Series
              </li>
            </ul>
          )}
        </div>
      </div>

      {/* Workspace nav */}
      <nav className={styles.nav}>
        {WORKSPACE_NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
            }
            onClick={() => selectProject(null)}
          >
            <span className={styles.navIcon}>{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Series pipeline nav — only when series is selected */}
      {currentProject && (
        <>
          <div className={styles.navDivider} />
          <nav className={styles.nav}>
            {SERIES_NAV.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `${styles.navItem} ${isActive ? styles.navItemActive : ''}`
                }
              >
                <span className={styles.navIcon}>{icon}</span>
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>
        </>
      )}

      {/* User section */}
      <div className={styles.userSection}>
        <div className={styles.userAvatar}>
          {currentWorkspace ? initials(currentWorkspace.name) : 'U'}
        </div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{currentWorkspace?.name ?? 'User'}</div>
          <div className={styles.userRole}>Studio Owner</div>
        </div>
        <button className={styles.logoutButton} onClick={logout} title="Sign out">⏻</button>
      </div>

      {showNewSeries && (
        <NewProjectModal
          onConfirm={handleCreateSeries}
          onCancel={() => setShowNewSeries(false)}
        />
      )}
    </aside>
  );
}
