import { apiClient } from './client';

export interface FeatureOverrideOut {
  provider: string | null;
  model: string | null;
  base_url: string | null;
  has_api_key: boolean;
}

export interface AIConfigOut {
  provider: string;
  model: string;
  base_url: string | null;
  has_api_key: boolean;
  feature_overrides: Record<string, FeatureOverrideOut>;
  features: { key: string; label: string }[];
}

export interface FeatureOverrideIn {
  provider?: string;
  model?: string;
  base_url?: string;
  api_key?: string;
}

export interface AIConfigUpdate {
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  feature_overrides: Record<string, FeatureOverrideIn>;
}

export async function fetchAIConfig(workspaceId: string): Promise<AIConfigOut> {
  const res = await apiClient.get(`/workspaces/${workspaceId}/ai-config`);
  return res.data;
}

export async function updateAIConfig(workspaceId: string, data: AIConfigUpdate): Promise<AIConfigOut> {
  const res = await apiClient.put(`/workspaces/${workspaceId}/ai-config`, data);
  return res.data;
}

export async function testAIConfig(workspaceId: string): Promise<{ status: string; provider?: string; model?: string; detail?: string }> {
  const res = await apiClient.post(`/workspaces/${workspaceId}/ai-config/test`);
  return res.data;
}
