import { useState, useEffect, FormEvent } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { useNavigate } from 'react-router-dom';
import { fetchAIConfig, updateAIConfig, testAIConfig } from '../api/aiConfig';
import type { AIConfigOut, AIConfigUpdate, FeatureOverrideIn } from '../api/aiConfig';
import styles from './Settings.module.css';
import aiStyles from './AIConfig.module.css';

const PROVIDERS = [
  { value: 'ollama',    label: 'Ollama (local)' },
  { value: 'openai',   label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const OLLAMA_MODELS  = ['kimi-k2.5:cloud', 'deepseek-coder-v2:lite', 'qwen2.5-coder:32b', 'llama3.1:8b'];
const OPENAI_MODELS  = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'];
const ANTHROPIC_MODELS = ['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'];

function modelsFor(provider: string) {
  if (provider === 'openai')    return OPENAI_MODELS;
  if (provider === 'anthropic') return ANTHROPIC_MODELS;
  return OLLAMA_MODELS;
}

export default function Settings() {
  const { currentWorkspace, refreshWorkspaces, deleteWorkspace } = useWorkspace();
  const navigate = useNavigate();

  // ── Workspace settings ───────────────────────────────────────────────────
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // ── AI config ────────────────────────────────────────────────────────────
  const [aiConfig, setAiConfig] = useState<AIConfigOut | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiProvider, setAiProvider]   = useState('ollama');
  const [aiModel, setAiModel]         = useState('');
  const [aiBaseUrl, setAiBaseUrl]     = useState('');
  const [aiApiKey, setAiApiKey]       = useState('');   // '' = unchanged
  const [aiSaving, setAiSaving]       = useState(false);
  const [aiSaved, setAiSaved]         = useState(false);
  const [aiError, setAiError]         = useState('');
  const [testStatus, setTestStatus]   = useState<null | 'testing' | 'ok' | 'error'>(null);
  const [testDetail, setTestDetail]   = useState('');

  // Per-feature overrides: featureKey → { provider, model, base_url, api_key }
  const [overrides, setOverrides] = useState<Record<string, FeatureOverrideIn>>({});
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
    setName(currentWorkspace.name);
    loadAIConfig();
  }, [currentWorkspace]);

  async function loadAIConfig() {
    if (!currentWorkspace) return;
    setAiLoading(true);
    try {
      const cfg = await fetchAIConfig(currentWorkspace.id);
      setAiConfig(cfg);
      setAiProvider(cfg.provider);
      setAiModel(cfg.model);
      setAiBaseUrl(cfg.base_url ?? '');
      // Populate overrides from existing config
      const ov: Record<string, FeatureOverrideIn> = {};
      for (const [key, val] of Object.entries(cfg.feature_overrides)) {
        ov[key] = { provider: val.provider ?? '', model: val.model ?? '', base_url: val.base_url ?? '' };
      }
      setOverrides(ov);
    } catch {
      setAiError('Failed to load AI config');
    } finally {
      setAiLoading(false);
    }
  }

  // ── Workspace handlers ───────────────────────────────────────────────────
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;
    setError('');
    setSaving(true);
    try {
      await refreshWorkspaces();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!currentWorkspace) return;
    setDeleting(true);
    try {
      await deleteWorkspace(currentWorkspace.id);
      navigate('/');
    } catch {
      setError('Failed to delete workspace');
      setDeleting(false);
      setShowDeleteConfirm(false);
    }
  };

  const handleYouTubeConnect = () => {
    if (!currentWorkspace) return;
    window.location.href = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/workspaces/${currentWorkspace.id}/youtube/connect`;
  };

  // ── AI config handlers ───────────────────────────────────────────────────
  const handleAISave = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;
    setAiError('');
    setAiSaving(true);
    try {
      const payload: AIConfigUpdate = {
        provider: aiProvider,
        model: aiModel,
        base_url: aiBaseUrl || undefined,
        api_key: aiApiKey || undefined,   // undefined = don't change
        feature_overrides: Object.fromEntries(
          Object.entries(overrides).filter(([, v]) => v.provider || v.model || v.base_url || v.api_key)
        ),
      };
      const updated = await updateAIConfig(currentWorkspace.id, payload);
      setAiConfig(updated);
      setAiApiKey('');  // clear after save
      setAiSaved(true);
      setTimeout(() => setAiSaved(false), 2000);
    } catch (err: unknown) {
      setAiError(err instanceof Error ? err.message : 'Failed to save AI config');
    } finally {
      setAiSaving(false);
    }
  };

  const handleTest = async () => {
    if (!currentWorkspace) return;
    setTestStatus('testing');
    setTestDetail('');
    try {
      const result = await testAIConfig(currentWorkspace.id);
      setTestStatus(result.status === 'ok' ? 'ok' : 'error');
      setTestDetail(result.status === 'ok'
        ? `Connected — ${result.provider} / ${result.model}`
        : result.detail ?? 'Unknown error');
    } catch {
      setTestStatus('error');
      setTestDetail('Request failed');
    }
  };

  const setOverrideField = (feature: string, field: keyof FeatureOverrideIn, value: string) => {
    setOverrides(prev => ({
      ...prev,
      [feature]: { ...prev[feature], [field]: value },
    }));
  };

  if (!currentWorkspace) {
    return (
      <main className={styles.container}>
        <p className={styles.empty}>No workspace selected. Create one first.</p>
      </main>
    );
  }

  return (
    <main className={styles.container}>
      <h1 className={styles.title}>Settings</h1>
      <p className={styles.subtitle}>Workspace: <strong>{currentWorkspace.name}</strong></p>

      {/* ── Workspace ── */}
      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.field}>
          <label className={styles.label}>Workspace name</label>
          <input className={`${styles.input} ${styles.inputReadonly}`} value={name} readOnly />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>YouTube channel</label>
          <div className={styles.youtubeRow}>
            <span className={styles.channelId}>
              {currentWorkspace.youtube_channel_id ?? 'Not connected'}
            </span>
            <button type="button" className={styles.connectButton} onClick={handleYouTubeConnect}>
              {currentWorkspace.youtube_channel_id ? 'Reconnect YouTube' : 'Connect YouTube'}
            </button>
          </div>
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <button type="submit" className={styles.saveButton} disabled={saving}>
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save changes'}
        </button>
      </form>

      {/* ── AI Configuration ── */}
      <div className={aiStyles.section}>
        <h2 className={aiStyles.sectionTitle}>AI Configuration</h2>
        <p className={aiStyles.sectionDesc}>
          Configure the AI model used for all AI features in this workspace. You can override the model per feature below.
        </p>

        {aiLoading ? (
          <p className={aiStyles.loading}>Loading…</p>
        ) : (
          <form className={aiStyles.form} onSubmit={handleAISave}>

            {/* Default config */}
            <div className={aiStyles.card}>
              <div className={aiStyles.cardTitle}>Default model</div>

              <div className={aiStyles.row}>
                <div className={aiStyles.field}>
                  <label className={aiStyles.label}>Provider</label>
                  <select
                    className={aiStyles.select}
                    value={aiProvider}
                    onChange={e => { setAiProvider(e.target.value); setAiModel(modelsFor(e.target.value)[0]); }}
                  >
                    {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                  </select>
                </div>

                <div className={aiStyles.field}>
                  <label className={aiStyles.label}>Model</label>
                  <input
                    className={aiStyles.input}
                    list="model-suggestions"
                    value={aiModel}
                    onChange={e => setAiModel(e.target.value)}
                    placeholder="e.g. kimi-k2.5:cloud"
                  />
                  <datalist id="model-suggestions">
                    {modelsFor(aiProvider).map(m => <option key={m} value={m} />)}
                  </datalist>
                </div>
              </div>

              {aiProvider === 'ollama' && (
                <div className={aiStyles.field}>
                  <label className={aiStyles.label}>Ollama base URL</label>
                  <input
                    className={aiStyles.input}
                    value={aiBaseUrl}
                    onChange={e => setAiBaseUrl(e.target.value)}
                    placeholder="http://localhost:11434"
                  />
                </div>
              )}

              {(aiProvider === 'openai' || aiProvider === 'anthropic') && (
                <div className={aiStyles.field}>
                  <label className={aiStyles.label}>
                    API key{aiConfig?.has_api_key ? ' (leave blank to keep existing)' : ''}
                  </label>
                  <input
                    className={aiStyles.input}
                    type="password"
                    value={aiApiKey}
                    onChange={e => setAiApiKey(e.target.value)}
                    placeholder={aiConfig?.has_api_key ? '••••••••••••••••' : 'sk-…'}
                    autoComplete="off"
                  />
                </div>
              )}

              {/* Test connection */}
              <div className={aiStyles.testRow}>
                <button type="button" className={aiStyles.testBtn} onClick={handleTest} disabled={testStatus === 'testing'}>
                  {testStatus === 'testing' ? 'Testing…' : 'Test connection'}
                </button>
                {testStatus === 'ok'    && <span className={aiStyles.testOk}>✓ {testDetail}</span>}
                {testStatus === 'error' && <span className={aiStyles.testErr}>✗ {testDetail}</span>}
              </div>
            </div>

            {/* Per-feature overrides */}
            {aiConfig && aiConfig.features.length > 0 && (
              <div className={aiStyles.card}>
                <div className={aiStyles.cardTitle}>Per-feature overrides</div>
                <p className={aiStyles.cardDesc}>Leave blank to use the default model above.</p>

                <div className={aiStyles.featureList}>
                  {aiConfig.features.map(({ key, label }) => {
                    const ov = overrides[key] ?? {};
                    const existing = aiConfig.feature_overrides[key];
                    const hasOverride = existing?.provider || existing?.model;
                    const isOpen = expandedFeature === key;

                    return (
                      <div key={key} className={aiStyles.featureItem}>
                        <button
                          type="button"
                          className={aiStyles.featureHeader}
                          onClick={() => setExpandedFeature(isOpen ? null : key)}
                        >
                          <span className={aiStyles.featureLabel}>{label}</span>
                          <span className={aiStyles.featureBadge}>
                            {hasOverride
                              ? `${existing.provider ?? aiProvider} / ${existing.model ?? aiModel}`
                              : <span className={aiStyles.featureDefault}>default</span>}
                          </span>
                          <span className={aiStyles.featureChevron}>{isOpen ? '▲' : '▼'}</span>
                        </button>

                        {isOpen && (
                          <div className={aiStyles.featureBody}>
                            <div className={aiStyles.row}>
                              <div className={aiStyles.field}>
                                <label className={aiStyles.label}>Provider</label>
                                <select
                                  className={aiStyles.select}
                                  value={ov.provider ?? ''}
                                  onChange={e => setOverrideField(key, 'provider', e.target.value)}
                                >
                                  <option value="">— use default —</option>
                                  {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                                </select>
                              </div>
                              <div className={aiStyles.field}>
                                <label className={aiStyles.label}>Model</label>
                                <input
                                  className={aiStyles.input}
                                  list={`model-opts-${key}`}
                                  value={ov.model ?? ''}
                                  onChange={e => setOverrideField(key, 'model', e.target.value)}
                                  placeholder="— use default —"
                                />
                                <datalist id={`model-opts-${key}`}>
                                  {modelsFor(ov.provider ?? aiProvider).map(m => <option key={m} value={m} />)}
                                </datalist>
                              </div>
                            </div>

                            {(ov.provider === 'ollama' || (!ov.provider && aiProvider === 'ollama')) && (
                              <div className={aiStyles.field}>
                                <label className={aiStyles.label}>Base URL override</label>
                                <input
                                  className={aiStyles.input}
                                  value={ov.base_url ?? ''}
                                  onChange={e => setOverrideField(key, 'base_url', e.target.value)}
                                  placeholder="http://localhost:11434"
                                />
                              </div>
                            )}

                            {((ov.provider ?? aiProvider) === 'openai' || (ov.provider ?? aiProvider) === 'anthropic') && (
                              <div className={aiStyles.field}>
                                <label className={aiStyles.label}>
                                  API key override{existing?.has_api_key ? ' (leave blank to keep existing)' : ''}
                                </label>
                                <input
                                  className={aiStyles.input}
                                  type="password"
                                  value={ov.api_key ?? ''}
                                  onChange={e => setOverrideField(key, 'api_key', e.target.value)}
                                  placeholder={existing?.has_api_key ? '••••••••••••••••' : 'sk-…'}
                                  autoComplete="off"
                                />
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {aiError && <p className={styles.error}>{aiError}</p>}

            <button type="submit" className={styles.saveButton} disabled={aiSaving}>
              {aiSaving ? 'Saving…' : aiSaved ? 'Saved ✓' : 'Save AI settings'}
            </button>
          </form>
        )}
      </div>

      {/* ── Danger zone ── */}
      <div className={styles.dangerZone}>
        <h2 className={styles.dangerTitle}>Danger zone</h2>
        <div className={styles.dangerRow}>
          <div>
            <div className={styles.dangerLabel}>Delete workspace</div>
            <div className={styles.dangerDesc}>Permanently delete this workspace and all its data. This cannot be undone.</div>
          </div>
          {!showDeleteConfirm ? (
            <button className={styles.deleteButton} onClick={() => setShowDeleteConfirm(true)}>
              Delete workspace
            </button>
          ) : (
            <div className={styles.confirmRow}>
              <span className={styles.confirmText}>Are you sure?</span>
              <button className={styles.confirmDeleteButton} onClick={handleDelete} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Yes, delete'}
              </button>
              <button className={styles.cancelDeleteButton} onClick={() => setShowDeleteConfirm(false)} disabled={deleting}>
                Cancel
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
