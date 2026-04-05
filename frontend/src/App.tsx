import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Sidebar } from './components/Sidebar';
import Dashboard from './pages/Dashboard';
import Tasks from './pages/Tasks';
import Scripts from './pages/Scripts';
import Talent from './pages/Talent';
import Analytics from './pages/Analytics';
import Settings from './pages/Settings';
import Login from './pages/Login';

function AppLayout() {
  const { isAuthenticated } = useAuth();

  if (!isAuthenticated) {
    return <Login />;
  }

  return (
    <div style={{ display: 'flex', height: '100%' }}>
      <Sidebar />
      <div style={{ flex: 1, overflow: 'auto' }}>
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/tasks"     element={<Tasks />} />
          <Route path="/scripts"   element={<Scripts />} />
          <Route path="/talent"    element={<Talent />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings"  element={<Settings />} />
          <Route path="*"          element={<Navigate to="/" replace />} />
        </Routes>
      </div>
    </div>
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
