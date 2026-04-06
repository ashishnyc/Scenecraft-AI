import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { apiClient } from '../api/client';

export interface Workspace {
  id: string;
  name: string;
  youtube_channel_id: string | null;
  created_at: string;
}

interface WorkspaceContextValue {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  loading: boolean;
  switchWorkspace: (id: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string, youtubeChannelId: string) => Promise<void>;
  deleteWorkspace: (id: string) => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

const WORKSPACE_KEY = 'sc_workspace_id';

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshWorkspaces = useCallback(async () => {
    try {
      const res = await apiClient.get<Workspace[]>('/workspaces');
      const list = res.data;
      setWorkspaces(list);

      const savedId = localStorage.getItem(WORKSPACE_KEY);
      const saved = list.find((w) => w.id === savedId) ?? list[0] ?? null;
      setCurrentWorkspace(saved);
      if (saved) localStorage.setItem(WORKSPACE_KEY, saved.id);
    } catch {
      // not authenticated yet or network error — fail silently
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refreshWorkspaces(); }, [refreshWorkspaces]);

  const switchWorkspace = useCallback((id: string) => {
    const ws = workspaces.find((w) => w.id === id);
    if (ws) {
      setCurrentWorkspace(ws);
      localStorage.setItem(WORKSPACE_KEY, ws.id);
    }
  }, [workspaces]);

  const createWorkspace = useCallback(async (name: string, youtubeChannelId: string) => {
    const res = await apiClient.post<Workspace>('/workspaces', { name, youtube_channel_id: youtubeChannelId });
    const created = res.data;
    setWorkspaces((prev) => [created, ...prev]);
    setCurrentWorkspace(created);
    localStorage.setItem(WORKSPACE_KEY, created.id);
  }, []);

  const deleteWorkspace = useCallback(async (id: string) => {
    await apiClient.delete(`/workspaces/${id}`);
    const remaining = workspaces.filter((w) => w.id !== id);
    setWorkspaces(remaining);
    if (currentWorkspace?.id === id) {
      const next = remaining[0] ?? null;
      setCurrentWorkspace(next);
      if (next) localStorage.setItem(WORKSPACE_KEY, next.id);
      else localStorage.removeItem(WORKSPACE_KEY);
    }
  }, [workspaces, currentWorkspace]);

  return (
    <WorkspaceContext.Provider value={{ workspaces, currentWorkspace, loading, switchWorkspace, refreshWorkspaces, createWorkspace, deleteWorkspace }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
