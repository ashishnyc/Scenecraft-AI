import { apiClient } from './client';

export type RoleType = 'lead' | 'supporting' | 'recurring' | 'narrator' | 'villain';
export type CastingRole = 'lead' | 'supporting' | 'recurring' | 'guest' | 'cameo';
export type CastingStatus = 'active' | 'written_out' | 'killed_off' | 'recurring';

export const ROLE_LABELS: Record<RoleType, string> = {
  lead: 'Lead',
  supporting: 'Supporting',
  recurring: 'Recurring',
  narrator: 'Narrator',
  villain: 'Villain',
};

export const CASTING_ROLE_LABELS: Record<CastingRole, string> = {
  lead: 'Lead',
  supporting: 'Supporting',
  recurring: 'Recurring',
  guest: 'Guest',
  cameo: 'Cameo',
};

export interface AppearanceVersion {
  id: string;
  label: string;
  description: string | null;
  image_url: string | null;
  created_at: string;
}

export interface VisualReferences {
  images: { url: string; filename: string; key: string }[];
}

export interface Character {
  id: string;
  account_id: string;
  name: string;
  role_type: RoleType;
  personality_prompt: string | null;
  backstory: string | null;
  age: number | null;
  lora_model_url: string | null;
  voice_profile_id: string | null;
  visual_references: VisualReferences | null;
  appearance_state: { versions: AppearanceVersion[]; active_version_id?: string } | null;
  engagement_stats: Record<string, unknown> | null;
  created_at: string;
}

export interface CharacterCreate {
  name: string;
  role_type: RoleType;
  personality_prompt?: string;
  backstory?: string;
  age?: number;
  voice_profile_id?: string;
}

export interface CharacterUpdate {
  name?: string;
  role_type?: RoleType;
  personality_prompt?: string;
  backstory?: string;
  age?: number;
  voice_profile_id?: string;
  lora_model_url?: string;
}

export interface Casting {
  id: string;
  character_id: string;
  project_id: string;
  role: CastingRole;
  character_arc_notes: string | null;
  first_episode: number | null;
  status: CastingStatus;
  appearance_override: Record<string, unknown> | null;
  character: Character;
}

export interface CastingCreate {
  character_id: string;
  role: CastingRole;
  character_arc_notes?: string;
  first_episode?: number;
}

export interface CharacterAnalytics {
  character_id: string;
  name: string;
  total_appearances: number;
  total_views: number;
  avg_views_per_appearance: number;
  top_project_id: string | null;
  engagement_breakdown: Record<string, number>;
}

// ── Character CRUD ────────────────────────────────────────────────────────────

export async function fetchCharacters(): Promise<Character[]> {
  const res = await apiClient.get<Character[]>('/characters');
  return res.data;
}

export async function fetchCharacter(id: string): Promise<Character> {
  const res = await apiClient.get<Character>(`/characters/${id}`);
  return res.data;
}

export async function createCharacter(body: CharacterCreate): Promise<Character> {
  const res = await apiClient.post<Character>('/characters', body);
  return res.data;
}

export async function updateCharacter(id: string, body: CharacterUpdate): Promise<Character> {
  const res = await apiClient.put<Character>(`/characters/${id}`, body);
  return res.data;
}

export async function deleteCharacter(id: string): Promise<void> {
  await apiClient.delete(`/characters/${id}`);
}

// ── Visual identity ───────────────────────────────────────────────────────────

export async function uploadVisualReference(id: string, file: File): Promise<Character> {
  const form = new FormData();
  form.append('file', file);
  const res = await apiClient.post<Character>(`/characters/${id}/visual-references`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
}

export async function addAppearanceVersion(
  id: string,
  body: { label: string; description?: string; image_url?: string }
): Promise<Character> {
  const res = await apiClient.post<Character>(`/characters/${id}/appearance-versions`, body);
  return res.data;
}

export async function setLoraModel(id: string, lora_model_url: string): Promise<Character> {
  const res = await apiClient.put<Character>(`/characters/${id}/lora-model`, { lora_model_url });
  return res.data;
}

// ── Casting ───────────────────────────────────────────────────────────────────

export async function fetchCast(projectId: string): Promise<Casting[]> {
  const res = await apiClient.get<Casting[]>(`/projects/${projectId}/cast`);
  return res.data;
}

export async function castCharacter(projectId: string, body: CastingCreate): Promise<Casting> {
  const res = await apiClient.post<Casting>(`/projects/${projectId}/cast`, body);
  return res.data;
}

export async function updateCasting(
  projectId: string,
  castingId: string,
  body: { role?: CastingRole; character_arc_notes?: string; status?: CastingStatus }
): Promise<Casting> {
  const res = await apiClient.put<Casting>(`/projects/${projectId}/cast/${castingId}`, body);
  return res.data;
}

export async function removeFromCast(projectId: string, castingId: string): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/cast/${castingId}`);
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export async function fetchCharacterAnalytics(id: string): Promise<CharacterAnalytics> {
  const res = await apiClient.get<CharacterAnalytics>(`/characters/${id}/analytics`);
  return res.data;
}

export async function fetchWorkspaceCharacterAnalytics(workspaceId: string): Promise<CharacterAnalytics[]> {
  const res = await apiClient.get<CharacterAnalytics[]>(`/workspaces/${workspaceId}/character-analytics`);
  return res.data;
}
