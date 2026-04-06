import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, useCallback } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { WorkspaceProvider, useWorkspace } from './context/WorkspaceContext';
import { ProjectProvider } from './context/ProjectContext';
import { Sidebar } from './components/Sidebar';
import PitchInbox from './components/PitchInbox';
import Dashboard from './pages/Dashboard';
import Tasks from './pages/Tasks';
import Scripts from './pages/Scripts';
import VideoReview from './pages/VideoReview';
import PublishWorkflow from './pages/PublishWorkflow';
import Talent from './pages/Talent';
import Analytics from './pages/Analytics';
import Instagram from './pages/Instagram';
import Settings from './pages/Settings';
import ProjectDetail from './pages/ProjectDetail';
import Login from './pages/Login';
import { fetchPitches } from './api/pitches';
import styles from './components/PitchInbox.module.css';

function InboxButton() {
  const { currentWorkspace } = useWorkspace();
  const [count, setCount] = useState(0);
  const [open, setOpen] = useState(false);

  const refresh = useCallback(async () => {
    if (!currentWorkspace) { setCount(0); return; }
    try {
      const pitches = await fetchPitches(currentWorkspace.id);
      setCount(pitches.filter((p) => p.status === 'pending' || p.status === 'low_originality').length);
    } catch {
      // ignore
    }
  }, [currentWorkspace]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <>
      <button className={styles.inboxBtn} onClick={() => setOpen(true)} aria-label="AI Inbox">
        AI Inbox
        {count > 0 && <span className={styles.badgeCount}>{count}</span>}
      </button>
      {open && <PitchInbox onClose={() => { setOpen(false); refresh(); }} />}
    </>
  );
}

function AppLayout() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <WorkspaceProvider>
    <ProjectProvider>
    <div style={{ display: 'flex', height: '100%' }}>
      <Sidebar />
      <div style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-3) var(--space-6)',
          borderBottom: '1px solid var(--color-border)',
          background: 'var(--color-bg-primary)',
          flexShrink: 0,
        }}>
          <InboxButton />
          <button style={{
            background: 'var(--gradient-accent)',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            color: '#fff',
            fontSize: 'var(--text-sm)',
            fontWeight: 600,
            padding: 'var(--space-2) var(--space-4)',
            cursor: 'pointer',
            fontFamily: 'inherit',
            boxShadow: 'var(--shadow-accent)',
          }}>
            + New Task
          </button>
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          <Routes>
            <Route path="/"          element={<Dashboard />} />
            <Route path="/tasks"     element={<Tasks />} />
            <Route path="/projects"  element={<ProjectDetail />} />
            <Route path="/scripts"   element={<Scripts />} />
            <Route path="/video-review" element={<VideoReview />} />
            <Route path="/publish"   element={<PublishWorkflow />} />
            <Route path="/talent"    element={<Talent />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/instagram" element={<Instagram />} />
            <Route path="/settings"  element={<Settings />} />
            <Route path="*"          element={<Navigate to="/" replace />} />
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
