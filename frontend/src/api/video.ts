import { apiClient } from './client';

export interface Shot {
  shot_index: number;
  scene_number: number;
  duration_seconds: number;
  environment: string;
  camera_angle: string;
  action_description: string;
  mood: string;
  characters: string[];
}

export interface QualityReport {
  passed: boolean;
  errors: string[];
  warnings: string[];
  details: Record<string, unknown>;
}

export interface VideoReviewData {
  task_id: string;
  title: string;
  status: string;
  shot_list: { shots: Shot[] };
  quality_report: QualityReport | null;
  total_cost_usd: string;
  hls_signed_url: string | null;
}

export interface ThumbnailOption {
  index: string;
  s3_url: string;
  signed_url: string;
  prompt: string;
}

export interface YoutubeMetadata {
  title: string;
  description: string;
  tags: string[];
  scheduled_at: string | null;
}

export async function getVideoReviewData(taskId: string): Promise<VideoReviewData> {
  const res = await apiClient.get<VideoReviewData>(`/tasks/${taskId}/video/review-data`);
  return res.data;
}

export async function createHlsPreview(taskId: string): Promise<{ master_url: string; signed_url: string }> {
  const res = await apiClient.post(`/tasks/${taskId}/video/hls-preview`);
  return res.data;
}

export async function approveVideo(taskId: string, notes: string): Promise<void> {
  await apiClient.post(`/tasks/${taskId}/video/feedback`, { action: 'approve', notes });
}

export async function requestVideoChanges(
  taskId: string,
  notes: string,
  flaggedShotIndices: number[],
): Promise<void> {
  await apiClient.post(`/tasks/${taskId}/video/feedback`, {
    action: 'request_changes',
    notes,
    flagged_shot_indices: flaggedShotIndices,
  });
}

export async function generateThumbnails(taskId: string): Promise<ThumbnailOption[]> {
  const res = await apiClient.post<{ task_id: string; options: ThumbnailOption[] }>(
    `/tasks/${taskId}/thumbnails/generate`,
  );
  return res.data.options;
}

export async function selectThumbnail(
  taskId: string,
  optionIndex: number,
): Promise<{ thumbnail_url: string }> {
  const res = await apiClient.post(`/tasks/${taskId}/thumbnails/select`, { option_index: optionIndex });
  return res.data;
}

export async function uploadCustomThumbnail(
  taskId: string,
  imageBase64: string,
): Promise<{ thumbnail_url: string }> {
  const res = await apiClient.post(`/tasks/${taskId}/thumbnails/select`, { custom_image_b64: imageBase64 });
  return res.data;
}

export async function generateMetadata(taskId: string): Promise<YoutubeMetadata> {
  const res = await apiClient.post<YoutubeMetadata>(`/tasks/${taskId}/metadata/generate`);
  return res.data;
}

export async function saveMetadata(taskId: string, data: YoutubeMetadata): Promise<YoutubeMetadata> {
  const res = await apiClient.put<{ youtube_metadata: YoutubeMetadata }>(`/tasks/${taskId}/metadata`, data);
  return res.data.youtube_metadata;
}

// ── SA-45: Analytics ─────────────────────────────────────────────────────────

export interface RetentionPoint {
  date: string;
  views: number;
  likes: number;
  view_growth_pct: number;
}

export interface TaskAnalytics {
  task_id: string;
  youtube_video_id: string | null;
  latest: { views?: number; likes?: number; comments?: number };
  retention_curve: RetentionPoint[];
  total_cost_usd: string;
}

export interface VideoSummary {
  task_id: string;
  title: string;
  youtube_video_id: string | null;
  views: number;
  likes: number;
  cost_usd: string;
}

export interface WorkspaceAnalyticsSummary {
  workspace_id: string;
  published_count: number;
  total_views: number;
  total_likes: number;
  total_cost_usd: number;
  videos: VideoSummary[];
}

export async function getTaskAnalytics(taskId: string): Promise<TaskAnalytics> {
  const res = await apiClient.get<TaskAnalytics>(`/tasks/${taskId}/analytics`);
  return res.data;
}

export async function pollAnalyticsNow(taskId: string): Promise<{ snapshot: Record<string, unknown> }> {
  const res = await apiClient.post(`/tasks/${taskId}/analytics/poll`);
  return res.data;
}

export async function getWorkspaceAnalyticsSummary(workspaceId: string): Promise<WorkspaceAnalyticsSummary> {
  const res = await apiClient.get<WorkspaceAnalyticsSummary>(`/workspaces/${workspaceId}/analytics/summary`);
  return res.data;
}
