import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import { NewProjectModal } from './NewProjectModal';
import { NewWorkspaceModal } from './NewWorkspaceModal';
import { createProject } from '../api/projects';
import styles from './Sidebar.module.css';

// Always visible (workspace-level)
const WORKSPACE_NAV = [
  { to: '/',          label: 'Dashboard',     icon: '▦' },
  { to: '/talent',    label: 'Talent Roster', icon: '◉' },
  { to: '/analytics', label: 'Analytics',     icon: '∿' },
  { to: '/instagram', label: 'Instagram',     icon: '⬡' },
  { to: '/settings',  label: 'Settings',      icon: '⚙' },
];

// Only visible when a series is selected
const SERIES_NAV = [
  { to: '/tasks',        label: 'Videos',        icon: '▤' },
  { to: '/scripts',      label: 'Script Review', icon: '✎' },
  { to: '/video-review', label: 'Video Review',  icon: '▶' },
  { to: '/publish',      label: 'Publish',       icon: '↑' },
];

function toHandle(name: string) {
  return '@' + name.toLowerCase().replace(/\s+/g, '');
}

function initials(name: string) {
  return name.split(' ').map((w) => w[0]).join('').slice(0, 2).toUpperCase();
}

export function Sidebar() {
  const { logout } = useAuth();
  const { workspaces, currentWorkspace, switchWorkspace, createWorkspace } = useWorkspace();
  const { projects, currentProject, selectProject, refreshProjects } = useProject();
  const navigate = useNavigate();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);
  const [showNewWorkspace, setShowNewWorkspace] = useState(false);

  const handleCreateProject = async (data: Parameters<typeof createProject>[1]) => {
    if (!currentWorkspace) return;
    await createProject(currentWorkspace.id, data);
    await refreshProjects();
    setShowNewProject(false);
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

      {/* Workspace switcher */}
      <div className={styles.workspaceSwitcher}>
        <div className={styles.workspaceLabelRow}>
          <span className={styles.workspaceLabel}>Workspace</span>
        </div>
        <div className={styles.dropdownWrapper}>
          <button
            className={styles.workspaceButton}
            onClick={() => setDropdownOpen((o) => !o)}
            aria-haspopup="listbox"
            aria-expanded={dropdownOpen}
          >
            {currentWorkspace?.name ?? 'No workspace'}
            {currentWorkspace && (
              <span className={styles.workspaceHandle}>
                {toHandle(currentWorkspace.name)}
              </span>
            )}
          </button>
          {dropdownOpen && (
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
              {workspaces.length > 0 && <hr className={styles.dropdownDivider} />}
              <li
                className={styles.dropdownNewWorkspace}
                onClick={() => { setDropdownOpen(false); setShowNewWorkspace(true); }}
              >
                + New workspace
              </li>
            </ul>
          )}
        </div>
      </div>

      {/* Workspace-level navigation */}
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

      {/* Series pipeline nav — only when a series is selected */}
      {currentProject && (
        <>
          <div className={styles.seriesContext}>
            <div className={styles.seriesContextLabel}>Current series</div>
            <div className={styles.seriesContextName}>{currentProject.name}</div>
            <button
              className={styles.seriesContextClose}
              onClick={() => { selectProject(null); }}
              title="Back to workspace"
            >
              ✕
            </button>
          </div>
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

      {/* Series section */}
      <div className={styles.projectsSection}>
        <div className={styles.projectsHeader}>
          <span className={styles.projectsLabel}>Series</span>
        </div>
        <ul className={styles.projectList}>
          {projects.map((p) => (
            <li key={p.id}>
              <button
                className={`${styles.projectItem} ${currentProject?.id === p.id ? styles.projectItemActive : ''}`}
                onClick={() => { selectProject(p); navigate('/projects'); }}
              >
                <span className={styles.projectDot} />
                {p.name}
              </button>
            </li>
          ))}
          <li>
            <button className={styles.newProjectBtn} onClick={() => setShowNewProject(true)}>
              + New Series
            </button>
          </li>
        </ul>
      </div>

      {/* User section */}
      <div className={styles.userSection}>
        <div className={styles.userAvatar}>
          {currentWorkspace ? initials(currentWorkspace.name) : 'U'}
        </div>
        <div className={styles.userInfo}>
          <div className={styles.userName}>{currentWorkspace?.name ?? 'User'}</div>
          <div className={styles.userRole}>Studio Owner</div>
        </div>
        <button className={styles.logoutButton} onClick={logout} title="Sign out">
          ⏻
        </button>
      </div>

      {showNewProject && (
        <NewProjectModal
          onConfirm={handleCreateProject}
          onCancel={() => setShowNewProject(false)}
        />
      )}

      {showNewWorkspace && (
        <NewWorkspaceModal
          onConfirm={async (name, channelId) => { await createWorkspace(name, channelId); setShowNewWorkspace(false); }}
          onCancel={() => setShowNewWorkspace(false)}
        />
      )}
    </aside>
  );
}
