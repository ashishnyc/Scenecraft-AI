import { useState, useEffect } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import {
  fetchAIConfig, createModelConfig, updateModelConfig,
  deleteModelConfig, setDefaultConfig, updateFeatureOverrides, testAIConfig,
} from '../api/aiConfig';
import type { AIConfigOut, ModelConfigOut, ModelConfigCreate } from '../api/aiConfig';
import styles from './Settings.module.css';
import ai from './AIConfig.module.css';

// ── Model form (create / edit) ───────────────────────────────────────────────

interface ModelFormProps {
  providers: { value: string; label: string }[];
  providerModels: Record<string, string[]>;
  initial?: ModelConfigOut;
  onSave: (data: ModelConfigCreate) => Promise<void>;
  onCancel: () => void;
}

function ModelForm({ providers, providerModels, initial, onSave, onCancel }: ModelFormProps) {
  const [name, setName]           = useState(initial?.name ?? '');
  const [provider, setProvider]   = useState(initial?.provider ?? providers[0]?.value ?? 'ollama');
  const [model, setModel]         = useState(initial?.model ?? '');
  const [baseUrl, setBaseUrl]     = useState(initial?.base_url ?? '');
  const [apiKey, setApiKey]       = useState('');
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? false);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');

  const models = providerModels[provider] ?? [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !model.trim()) { setError('Name and model are required.'); return; }
    setSaving(true);
    setError('');
    try {
      await onSave({ name, provider, model, base_url: baseUrl || undefined, api_key: apiKey || undefined, is_default: isDefault });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save');
      setSaving(false);
    }
  };

  return (
    <form className={ai.modelForm} onSubmit={handleSubmit}>
      <div className={ai.row}>
        <div className={ai.field}>
          <label className={ai.label}>Config name</label>
          <input className={ai.input} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. Script Writer" />
        </div>
        <div className={ai.field}>
          <label className={ai.label}>Provider</label>
          <select className={ai.select} value={provider} onChange={e => { setProvider(e.target.value); setModel(providerModels[e.target.value]?.[0] ?? ''); }}>
            {providers.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
      </div>

      <div className={ai.field}>
        <label className={ai.label}>Model</label>
        <select className={ai.select} value={model} onChange={e => setModel(e.target.value)}>
          <option value="">— select —</option>
          {models.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>

      {provider === 'ollama' && (
        <div className={ai.field}>
          <label className={ai.label}>Base URL</label>
          <input className={ai.input} value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="http://localhost:11434" />
        </div>
      )}

      {(provider === 'openai' || provider === 'anthropic') && (
        <div className={ai.field}>
          <label className={ai.label}>
            API key{initial?.has_api_key ? ' (leave blank to keep existing)' : ''}
          </label>
          <input className={ai.input} type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
            placeholder={initial?.has_api_key ? '••••••••••••••••' : 'sk-…'} autoComplete="off" />
        </div>
      )}

      <label className={ai.checkRow}>
        <input type="checkbox" checked={isDefault} onChange={e => setIsDefault(e.target.checked)} />
        <span>Set as workspace default</span>
      </label>

      {error && <p className={styles.error}>{error}</p>}

      <div className={ai.formActions}>
        <button type="submit" className={styles.saveButton} disabled={saving}>
          {saving ? 'Saving…' : initial ? 'Update' : 'Create'}
        </button>
        <button type="button" className={ai.cancelBtn} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

// ── Main page ────────────────────────────────────────────────────────────────

export default function AIConfigPage() {
  const { currentWorkspace } = useWorkspace();
  const [config, setConfig]           = useState<AIConfigOut | null>(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState('');
  const [showForm, setShowForm]       = useState(false);
  const [editingId, setEditingId]     = useState<string | null>(null);
  const [deletingId, setDeletingId]   = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState('');
  const [testStatus, setTestStatus]   = useState<null | 'testing' | 'ok' | 'error'>(null);
  const [testDetail, setTestDetail]   = useState('');
  const [savingOverride, setSavingOverride] = useState(false);

  useEffect(() => { if (currentWorkspace) load(); }, [currentWorkspace]);

  async function load() {
    if (!currentWorkspace) return;
    setLoading(true);
    try { setConfig(await fetchAIConfig(currentWorkspace.id)); }
    catch { setError('Failed to load AI configuration'); }
    finally { setLoading(false); }
  }

  async function handleCreate(data: ModelConfigCreate) {
    if (!currentWorkspace) return;
    setConfig(await (async () => { await createModelConfig(currentWorkspace.id, data); return fetchAIConfig(currentWorkspace.id); })());
    setShowForm(false);
  }

  async function handleUpdate(id: string, data: ModelConfigCreate) {
    if (!currentWorkspace) return;
    await updateModelConfig(currentWorkspace.id, id, data);
    setConfig(await fetchAIConfig(currentWorkspace.id));
    setEditingId(null);
  }

  async function handleDelete(id: string) {
    if (!currentWorkspace) return;
    setDeleteError('');
    try {
      await deleteModelConfig(currentWorkspace.id, id);
      setConfig(await fetchAIConfig(currentWorkspace.id));
      setDeletingId(null);
    } catch (err: unknown) {
      setDeleteError(err instanceof Error ? err.message : 'Cannot delete');
    }
  }

  async function handleSetDefault(id: string) {
    if (!currentWorkspace) return;
    setConfig(await setDefaultConfig(currentWorkspace.id, id));
  }

  async function handleOverrideChange(feature: string, configId: string | null) {
    if (!currentWorkspace || !config) return;
    setSavingOverride(true);
    try {
      setConfig(await updateFeatureOverrides(currentWorkspace.id, { [feature]: configId }));
    } finally {
      setSavingOverride(false);
    }
  }

  async function handleTest() {
    if (!currentWorkspace) return;
    setTestStatus('testing');
    setTestDetail('');
    try {
      const result = await testAIConfig(currentWorkspace.id);
      setTestStatus(result.status === 'ok' ? 'ok' : 'error');
      setTestDetail(result.status === 'ok' ? `Connected — ${result.provider} / ${result.model}` : result.detail ?? 'Error');
    } catch {
      setTestStatus('error');
      setTestDetail('Request failed');
    }
  }

  if (!currentWorkspace) return <main className={styles.container}><p className={styles.empty}>No workspace selected.</p></main>;

  return (
    <main className={styles.container}>
      <h1 className={styles.title}>AI Configuration</h1>
      <p className={styles.subtitle}>Named model configurations for <strong>{currentWorkspace.name}</strong></p>

      {loading && <p className={ai.loading}>Loading…</p>}
      {error   && <p className={styles.error}>{error}</p>}

      {config && (
        <>
          {/* ── Model Configurations ── */}
          <section className={ai.section}>
            <div className={ai.sectionHeader}>
              <div>
                <div className={ai.sectionTitle}>Model Configurations</div>
                <div className={ai.sectionDesc}>Create named configs (e.g. "Script Writer") and assign them to features.</div>
              </div>
              {!showForm && (
                <button className={ai.addBtn} onClick={() => { setShowForm(true); setEditingId(null); }}>
                  + Add configuration
                </button>
              )}
            </div>

            {showForm && (
              <div className={ai.card}>
                <div className={ai.cardTitle}>New configuration</div>
                <ModelForm
                  providers={config.providers}
                  providerModels={config.provider_models}
                  onSave={handleCreate}
                  onCancel={() => setShowForm(false)}
                />
              </div>
            )}

            {config.model_configs.length === 0 && !showForm && (
              <p className={ai.empty}>No configurations yet. Add one to get started.</p>
            )}

            <div className={ai.configList}>
              {config.model_configs.map(mc => (
                <div key={mc.id} className={`${ai.configCard} ${mc.is_default ? ai.configCardDefault : ''}`}>
                  {editingId === mc.id ? (
                    <>
                      <div className={ai.cardTitle}>Edit — {mc.name}</div>
                      <ModelForm
                        providers={config.providers}
                        providerModels={config.provider_models}
                        initial={mc}
                        onSave={data => handleUpdate(mc.id, data)}
                        onCancel={() => setEditingId(null)}
                      />
                    </>
                  ) : (
                    <>
                      <div className={ai.configCardTop}>
                        <div className={ai.configCardName}>
                          {mc.name}
                          {mc.is_default && <span className={ai.defaultBadge}>Default</span>}
                        </div>
                        <div className={ai.configCardMeta}>
                          <span className={ai.pill}>{mc.provider}</span>
                          <span className={ai.pill}>{mc.model}</span>
                          {mc.base_url && <span className={ai.pillMuted}>{mc.base_url}</span>}
                          {mc.has_api_key && <span className={ai.pillMuted}>API key ••••</span>}
                        </div>
                      </div>
                      <div className={ai.configCardActions}>
                        {!mc.is_default && (
                          <button className={ai.actionBtn} onClick={() => handleSetDefault(mc.id)}>Set default</button>
                        )}
                        <button className={ai.actionBtn} onClick={() => { setEditingId(mc.id); setShowForm(false); }}>Edit</button>
                        {deletingId === mc.id ? (
                          <span className={ai.deleteConfirm}>
                            Sure?{' '}
                            <button className={ai.actionBtnDanger} onClick={() => handleDelete(mc.id)}>Delete</button>
                            {' '}
                            <button className={ai.actionBtn} onClick={() => { setDeletingId(null); setDeleteError(''); }}>Cancel</button>
                            {deleteError && <span className={ai.deleteErr}> {deleteError}</span>}
                          </span>
                        ) : (
                          <button className={ai.actionBtnDanger} onClick={() => { setDeletingId(mc.id); setDeleteError(''); }}>Delete</button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          </section>

          {/* ── Test connection ── */}
          {config.model_configs.length > 0 && (
            <div className={ai.testRow}>
              <button className={ai.testBtn} onClick={handleTest} disabled={testStatus === 'testing'}>
                {testStatus === 'testing' ? 'Testing…' : 'Test default connection'}
              </button>
              {testStatus === 'ok'    && <span className={ai.testOk}>✓ {testDetail}</span>}
              {testStatus === 'error' && <span className={ai.testErr}>✗ {testDetail}</span>}
            </div>
          )}

          {/* ── Feature Overrides ── */}
          {config.model_configs.length > 0 && (
            <section className={ai.section}>
              <div className={ai.sectionTitle}>Feature Overrides</div>
              <div className={ai.sectionDesc}>
                Choose which configuration to use per feature. Leave on "Default" to use the workspace default.
                {savingOverride && <span className={ai.saving}> Saving…</span>}
              </div>

              <div className={ai.featureTable}>
                {config.features.map(({ key, label }) => {
                  const current = config.feature_overrides[key] ?? '';
                  return (
                    <div key={key} className={ai.featureRow}>
                      <span className={ai.featureRowLabel}>{label}</span>
                      <select
                        className={ai.featureSelect}
                        value={current}
                        onChange={e => handleOverrideChange(key, e.target.value || null)}
                        disabled={savingOverride}
                      >
                        <option value="">— Default —</option>
                        {config.model_configs.map(mc => (
                          <option key={mc.id} value={mc.id}>{mc.name}</option>
                        ))}
                      </select>
                    </div>
                  );
                })}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
