import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WorkspaceProvider, useWorkspace } from './context/WorkspaceContext';
import { ProjectProvider } from './context/ProjectContext';
import { Sidebar } from './components/Sidebar';
import { NewWorkspaceModal } from './components/NewWorkspaceModal';
import { WorkspaceModal } from './components/WorkspaceModal';
import Tasks from './pages/Tasks';
import SeriesDashboard from './pages/SeriesDashboard';
import VideoTable from './pages/VideoTable';
import ProjectDetail from './pages/ProjectDetail';
import Login from './pages/Login';
import styles from './App.module.css';

function WorkspaceSwitcher() {
  const { workspaces, currentWorkspace, switchWorkspace, createWorkspace } = useWorkspace();
  const [open, setOpen] = useState(false);
  const [showNew, setShowNew] = useState(false);

  return (
    <div className={styles.wsSwitcher}>
      <button className={styles.wsButton} onClick={() => setOpen((o) => !o)}>
        <span className={styles.wsAvatar}>
          {currentWorkspace?.name.slice(0, 2).toUpperCase() ?? '??'}
        </span>
        <span className={styles.wsName}>{currentWorkspace?.name ?? 'No workspace'}</span>
        <span className={styles.wsChevron}>▾</span>
      </button>

      {open && (
        <ul className={styles.wsDropdown} onClick={() => setOpen(false)}>
          {workspaces.map((ws) => (
            <li
              key={ws.id}
              className={`${styles.wsItem} ${ws.id === currentWorkspace?.id ? styles.wsItemActive : ''}`}
              onClick={() => switchWorkspace(ws.id)}
            >
              <span className={styles.wsItemAvatar}>{ws.name.slice(0, 2).toUpperCase()}</span>
              {ws.name}
            </li>
          ))}
          {workspaces.length > 0 && <hr className={styles.wsDivider} />}
          <li className={styles.wsNewItem} onClick={() => { setOpen(false); setShowNew(true); }}>
            + New workspace
          </li>
        </ul>
      )}

      {showNew && (
        <NewWorkspaceModal
          onConfirm={async (name, channelId) => { await createWorkspace(name, channelId); setShowNew(false); }}
          onCancel={() => setShowNew(false)}
        />
      )}
    </div>
  );
}

function TopBar() {
  const [wsModalOpen, setWsModalOpen] = useState(false);
  return (
    <div className={styles.topBar}>
      <button
        className={styles.cogBtn}
        onClick={() => setWsModalOpen(true)}
        aria-label="Workspace overview"
        title="Dashboard, Analytics, Settings…"
      >
        ⚙
      </button>
      <WorkspaceSwitcher />
      {wsModalOpen && <WorkspaceModal onClose={() => setWsModalOpen(false)} />}
    </div>
  );
}

function AppLayout() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) return <Login />;

  return (
    <WorkspaceProvider>
    <ProjectProvider>
      <div className={styles.shell}>
        <Sidebar />
        <div className={styles.main}>
          <TopBar />
          <div className={styles.content}>
            <Routes>
              <Route path="/dashboard"    element={<SeriesDashboard />} />
              <Route path="/table"        element={<VideoTable />} />
              <Route path="/tasks"        element={<Tasks />} />
              <Route path="/projects"     element={<ProjectDetail />} />
              <Route path="*"             element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </div>
        </div>
      </div>
    </ProjectProvider>
    </WorkspaceProvider>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppLayout />
      </AuthProvider>
    </BrowserRouter>
  );
}
