import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { apiClient } from '../api/client';

export interface Workspace {
  id: string;
  name: string;
  youtube_channel_id: string | null;
  style_guide: Record<string, unknown> | null;
  upload_schedule: Record<string, unknown> | null;
  competitor_channels: string[] | null;
  created_at: string;
}

interface WorkspaceContextValue {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  loading: boolean;
  switchWorkspace: (id: string) => void;
  refreshWorkspaces: () => Promise<void>;
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

  return (
    <WorkspaceContext.Provider value={{ workspaces, currentWorkspace, loading, switchWorkspace, refreshWorkspaces }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used within WorkspaceProvider');
  return ctx;
}
