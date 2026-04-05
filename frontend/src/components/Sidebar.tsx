import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useWorkspace } from '../context/WorkspaceContext';
import { useProject } from '../context/ProjectContext';
import { NewProjectModal } from './NewProjectModal';
import { createProject } from '../api/projects';
import styles from './Sidebar.module.css';

const NAV_ITEMS = [
  { to: '/',             label: 'Dashboard',     icon: '⬛' },
  { to: '/tasks',        label: 'Tasks',         icon: '📋' },
  { to: '/scripts',      label: 'Script Review', icon: '📝' },
  { to: '/video-review', label: 'Video Review',  icon: '🎬' },
  { to: '/publish',      label: 'Publish',       icon: '🚀' },
  { to: '/talent',       label: 'Talent Roster', icon: '🎭' },
  { to: '/analytics',    label: 'Analytics',     icon: '📊' },
  { to: '/settings',     label: 'Settings',      icon: '⚙️' },
];

export function Sidebar() {
  const { logout } = useAuth();
  const { workspaces, currentWorkspace, switchWorkspace } = useWorkspace();
  const { projects, currentProject, selectProject, refreshProjects } = useProject();
  const navigate = useNavigate();

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [showNewProject, setShowNewProject] = useState(false);

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
            onClick={() => selectProject(null)}
          >
            <span className={styles.navIcon}>{icon}</span>
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Projects section */}
      <div className={styles.projectsSection}>
        <div className={styles.projectsHeader}>
          <span className={styles.projectsLabel}>Projects</span>
          <button
            className={styles.addProjectBtn}
            onClick={() => setShowNewProject(true)}
            title="New project"
          >
            +
          </button>
        </div>
        <ul className={styles.projectList}>
          {projects.map((p) => (
            <li key={p.id}>
              <button
                className={`${styles.projectItem} ${currentProject?.id === p.id ? styles.projectItemActive : ''}`}
                onClick={() => {
                  selectProject(p);
                  navigate('/projects');
                }}
              >
                <span className={styles.projectDot} />
                {p.name}
              </button>
            </li>
          ))}
          {projects.length === 0 && (
            <li className={styles.projectEmpty}>No projects yet</li>
          )}
        </ul>
      </div>

      {/* Logout */}
      <button className={styles.logoutButton} onClick={logout}>
        Sign out
      </button>

      {showNewProject && (
        <NewProjectModal
          onConfirm={handleCreateProject}
          onCancel={() => setShowNewProject(false)}
        />
      )}
    </aside>
  );
}
