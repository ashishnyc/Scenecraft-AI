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
  | 'brainstorm' | 'idea_review'
  | 'outline' | 'writing_review'
  | 'generate_script' | 'script_review'
  | 'generate_clips' | 'assemble_clips' | 'video_review'
  | 'prepare_metadata' | 'publish' | 'closed';

export const TASK_STATUSES: TaskStatus[] = [
  'brainstorm', 'idea_review',
  'outline', 'writing_review',
  'generate_script', 'script_review',
  'generate_clips', 'assemble_clips', 'video_review',
  'prepare_metadata', 'publish', 'closed',
];

export const STATUS_LABELS: Record<TaskStatus, string> = {
  brainstorm:      'Brainstorm',
  idea_review:     'Pending Review',
  outline:         'Outline',
  writing_review:  'Pending Review',
  generate_script: 'Generate Script',
  script_review:   'Pending Review',
  generate_clips:  'Generate Clips',
  assemble_clips:  'Assemble Clips',
  video_review:    'Pending Review',
  prepare_metadata:'Prepare Metadata',
  publish:         'Publish',
  closed:          'Closed',
};

export const STAGE_LABEL: Record<TaskStatus, string> = {
  brainstorm:      'Idea',
  idea_review:     'Idea',
  outline:         'Writing',
  writing_review:  'Writing',
  generate_script: 'Scripting',
  script_review:   'Scripting',
  generate_clips:  'Video',
  assemble_clips:  'Video',
  video_review:    'Video',
  prepare_metadata:'Upload',
  publish:         'Upload',
  closed:          'Upload',
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

export async function deleteTask(taskId: string): Promise<void> {
  await apiClient.delete(`/tasks/${taskId}`);
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
