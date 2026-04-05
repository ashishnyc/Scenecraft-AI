import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import type { Project } from '../api/projects';
import { fetchProjects } from '../api/projects';
import { useWorkspace } from './WorkspaceContext';

interface ProjectContextValue {
  projects: Project[];
  currentProject: Project | null;
  loading: boolean;
  selectProject: (project: Project | null) => void;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const { currentWorkspace } = useWorkspace();
  const [projects, setProjects] = useState<Project[]>([]);
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [loading, setLoading] = useState(false);

  const refreshProjects = useCallback(async () => {
    if (!currentWorkspace) { setProjects([]); setCurrentProject(null); return; }
    setLoading(true);
    try {
      const list = await fetchProjects(currentWorkspace.id);
      setProjects(list);
      // Keep currentProject in sync if it still exists
      setCurrentProject((prev) => prev ? (list.find((p) => p.id === prev.id) ?? null) : null);
    } catch {
      // fail silently
    } finally {
      setLoading(false);
    }
  }, [currentWorkspace]);

  useEffect(() => { refreshProjects(); }, [refreshProjects]);

  const selectProject = useCallback((project: Project | null) => {
    setCurrentProject(project);
  }, []);

  return (
    <ProjectContext.Provider value={{ projects, currentProject, loading, selectProject, refreshProjects }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProject must be used within ProjectProvider');
  return ctx;
}
