import { apiClient } from './client';

export interface StemEntry {
  line_index: number;
  s3_url: string;
  scene_number: number;
  character_name: string;
  duration_ms: number;
  approved: boolean;
}

export interface AudioStems {
  stems: StemEntry[];
  preview_url: string;
  chapter_timestamps: Record<number, number>; // scene_number → start_ms
  approved: boolean;
}

export async function fetchAudioPreviewUrl(taskId: string): Promise<string | null> {
  const res = await apiClient.get<{ preview_url: string }>(`/tasks/${taskId}/audio/preview`);
  return res.data.preview_url ?? null;
}

export async function approveAudio(taskId: string): Promise<void> {
  await apiClient.post(`/tasks/${taskId}/transition`, { status: 'script_review' });
}

export async function requestAudioChanges(
  taskId: string,
  sceneNotes: Record<number, string>,
  changedSceneNumbers: number[],
): Promise<void> {
  await apiClient.post(`/tasks/${taskId}/transition`, {
    status: 'audio_preview',
    changed_scene_numbers: changedSceneNumbers,
    scene_notes: sceneNotes,
  });
}
