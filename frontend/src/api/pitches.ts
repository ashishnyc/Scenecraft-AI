import { apiClient } from './client';
import type { Task } from './tasks';

export interface Pitch {
  id: string;
  workspace_id: string;
  title: string;
  concept_summary: string;
  target_audience_hook: string | null;
  appeal_score: number | null;
  source_topics: string[] | null;
  originality_score: number | null;
  similar_videos: { title: string; video_id: string }[] | null;
  notes: string | null;
  status: string;
  created_at: string;
}

export async function fetchPitches(workspaceId: string, status?: string): Promise<Pitch[]> {
  const params: Record<string, string> = {};
  if (status) params.status = status;
  const res = await apiClient.get<{ workspace_id: string; pitches: Pitch[] }>(
    `/workspaces/${workspaceId}/pitches`,
    { params },
  );
  return res.data.pitches;
}

export async function approvePitch(
  workspaceId: string,
  pitchId: string,
  projectId?: string,
): Promise<Task> {
  const res = await apiClient.post<Task>(
    `/workspaces/${workspaceId}/pitches/${pitchId}/approve`,
    { project_id: projectId ?? null },
  );
  return res.data;
}

export async function rejectPitch(workspaceId: string, pitchId: string): Promise<Pitch> {
  const res = await apiClient.post<Pitch>(
    `/workspaces/${workspaceId}/pitches/${pitchId}/reject`,
  );
  return res.data;
}

export async function updatePitchNotes(
  workspaceId: string,
  pitchId: string,
  notes: string,
): Promise<Pitch> {
  const res = await apiClient.patch<Pitch>(
    `/workspaces/${workspaceId}/pitches/${pitchId}/notes`,
    { notes },
  );
  return res.data;
}
