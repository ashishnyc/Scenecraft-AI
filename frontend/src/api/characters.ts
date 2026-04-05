import { apiClient } from './client';

export type RoleType = 'lead' | 'supporting' | 'recurring' | 'narrator' | 'villain';

export const ROLE_LABELS: Record<RoleType, string> = {
  lead: 'Lead',
  supporting: 'Supporting',
  recurring: 'Recurring',
  narrator: 'Narrator',
  villain: 'Villain',
};

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
}

export interface CharacterCreate {
  name: string;
  role_type: RoleType;
  personality_prompt?: string;
  backstory?: string;
  age?: number;
}

export async function fetchCharacters(): Promise<Character[]> {
  const res = await apiClient.get<Character[]>('/characters');
  return res.data;
}

export async function createCharacter(body: CharacterCreate): Promise<Character> {
  const res = await apiClient.post<Character>('/characters', body);
  return res.data;
}

export async function deleteCharacter(id: string): Promise<void> {
  await apiClient.delete(`/characters/${id}`);
}
