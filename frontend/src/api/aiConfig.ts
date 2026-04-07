import { apiClient } from './client';

export interface ModelConfigOut {
  id: string;
  name: string;
  provider: string;
  model: string;
  base_url: string | null;
  has_api_key: boolean;
  is_default: boolean;
}

export interface AIConfigOut {
  default_config_id: string | null;
  feature_overrides: Record<string, string>;   // feature → config_id
  model_configs: ModelConfigOut[];
  features: { key: string; label: string }[];
  providers: { value: string; label: string }[];
  provider_models: Record<string, string[]>;
}

export interface ModelConfigCreate {
  name: string;
  provider: string;
  model: string;
  base_url?: string;
  api_key?: string;
  is_default?: boolean;
}

export interface ModelConfigUpdate extends ModelConfigCreate {}

export async function fetchAIConfig(workspaceId: string): Promise<AIConfigOut> {
  const res = await apiClient.get(`/workspaces/${workspaceId}/ai-config`);
  return res.data;
}

export async function createModelConfig(workspaceId: string, data: ModelConfigCreate): Promise<ModelConfigOut> {
  const res = await apiClient.post(`/workspaces/${workspaceId}/ai-model-configs`, data);
  return res.data;
}

export async function updateModelConfig(workspaceId: string, configId: string, data: ModelConfigUpdate): Promise<ModelConfigOut> {
  const res = await apiClient.put(`/workspaces/${workspaceId}/ai-model-configs/${configId}`, data);
  return res.data;
}

export async function deleteModelConfig(workspaceId: string, configId: string): Promise<void> {
  await apiClient.delete(`/workspaces/${workspaceId}/ai-model-configs/${configId}`);
}

export async function setDefaultConfig(workspaceId: string, configId: string): Promise<AIConfigOut> {
  const res = await apiClient.put(`/workspaces/${workspaceId}/ai-config/default/${configId}`);
  return res.data;
}

export async function updateFeatureOverrides(
  workspaceId: string,
  overrides: Record<string, string | null>
): Promise<AIConfigOut> {
  const res = await apiClient.put(`/workspaces/${workspaceId}/ai-config/overrides`, { overrides });
  return res.data;
}

export async function testAIConfig(workspaceId: string): Promise<{ status: string; provider?: string; model?: string; detail?: string }> {
  const res = await apiClient.post(`/workspaces/${workspaceId}/ai-config/test`);
  return res.data;
}
