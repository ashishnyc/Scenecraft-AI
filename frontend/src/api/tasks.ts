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

export async function createTask(projectId: string, title: string, conceptBrief?: string): Promise<Task> {
  const res = await apiClient.post<Task>(`/projects/${projectId}/tasks`, {
    title,
    concept_brief: conceptBrief ?? null,
  });
  return res.data;
}

export async function updateTask(taskId: string, body: { title?: string; concept_brief?: string; creator_notes?: string }): Promise<Task> {
  const res = await apiClient.put<Task>(`/tasks/${taskId}`, body);
  return res.data;
}

export async function generateBrief(taskId: string): Promise<string> {
  const res = await apiClient.post<{ concept_brief: string }>(`/tasks/${taskId}/generate-brief`);
  return res.data.concept_brief;
}

export interface OriginalityResult {
  originality_score: number;
  max_similarity: number;
  low_originality: boolean;
  similar_videos: { title: string; video_id: string; score: number }[];
}

export async function checkOriginality(taskId: string): Promise<OriginalityResult> {
  const res = await apiClient.post<OriginalityResult>(`/tasks/${taskId}/check-originality`);
  return res.data;
}
