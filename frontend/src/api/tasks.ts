import { apiClient } from './client';

export interface Task {
  id: string;
  project_id: string;
  title: string;
  status: TaskStatus;
  concept_brief: string | null;
  creator_notes: string | null;
  script: Record<string, unknown> | null;
  final_video_url: string | null;
  youtube_video_id: string | null;
  total_cost_usd: string | null;
}

export type TaskStatus =
  | 'idea' | 'approved' | 'scripting' | 'audio_preview'
  | 'script_review' | 'producing' | 'final_review' | 'scheduled' | 'published';

export const TASK_STATUSES: TaskStatus[] = [
  'idea', 'approved', 'scripting', 'audio_preview',
  'script_review', 'producing', 'final_review', 'scheduled', 'published',
];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  idea: 'Idea',
  approved: 'Approved',
  scripting: 'Scripting',
  audio_preview: 'Audio Preview',
  script_review: 'Script Review',
  producing: 'Producing',
  final_review: 'Final Review',
  scheduled: 'Scheduled',
  published: 'Published',
};

export async function fetchTasksForWorkspace(workspaceId: string): Promise<Task[]> {
  // Fetch all projects for workspace, then all tasks for each project
  const projectsRes = await apiClient.get<{ id: string; name: string }[]>(`/workspaces/${workspaceId}/projects`);
  const projects = projectsRes.data;
  const taskArrays = await Promise.all(
    projects.map((p) => apiClient.get<Task[]>(`/projects/${p.id}/tasks`).then((r) => r.data))
  );
  return taskArrays.flat();
}

export async function transitionTask(taskId: string, status: TaskStatus): Promise<Task> {
  const res = await apiClient.post<Task>(`/tasks/${taskId}/transition`, { status });
  return res.data;
}

export async function createTask(projectId: string, title: string): Promise<Task> {
  const res = await apiClient.post<Task>(`/projects/${projectId}/tasks`, { title });
  return res.data;
}
