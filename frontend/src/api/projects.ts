import { apiClient } from './client';

export type ProjectType = 'serialised' | 'anthology';
export type ProjectStatus = 'active' | 'completed' | 'paused';

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  type: ProjectType;
  story_bible: Record<string, unknown> | null;
  status: ProjectStatus;
  episode_count: number | null;
}

export interface ProjectCreate {
  name: string;
  type: ProjectType;
  episode_count?: number;
  story_bible?: Record<string, unknown>;
}

export interface ProjectUpdate {
  name?: string;
  story_bible?: Record<string, unknown>;
  status?: ProjectStatus;
  episode_count?: number;
}

export async function fetchProjects(workspaceId: string): Promise<Project[]> {
  const res = await apiClient.get<Project[]>(`/workspaces/${workspaceId}/projects`);
  return res.data;
}

export async function createProject(workspaceId: string, body: ProjectCreate): Promise<Project> {
  const res = await apiClient.post<Project>(`/workspaces/${workspaceId}/projects`, body);
  return res.data;
}

export async function updateProject(projectId: string, body: ProjectUpdate): Promise<Project> {
  const res = await apiClient.put<Project>(`/projects/${projectId}`, body);
  return res.data;
}

export async function deleteProject(projectId: string): Promise<void> {
  await apiClient.delete(`/projects/${projectId}`);
}

export interface VideoConceptSuggestion {
  title: string;
  concept: string;
}

export interface ProjectSuggestion {
  name: string;
  series_concept: string;
  video_concepts: VideoConceptSuggestion[];
}

export async function suggestProject(workspaceId: string, brief: string): Promise<ProjectSuggestion> {
  const res = await apiClient.post<ProjectSuggestion>(
    `/workspaces/${workspaceId}/projects/suggest`,
    { brief },
  );
  return res.data;
}
