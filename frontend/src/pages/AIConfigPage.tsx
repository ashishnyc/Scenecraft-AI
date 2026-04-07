import { useState, useEffect, FormEvent } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { fetchAIConfig, updateAIConfig, testAIConfig } from '../api/aiConfig';
import type { AIConfigOut, AIConfigUpdate, FeatureOverrideIn } from '../api/aiConfig';
import styles from './Settings.module.css';
import aiStyles from './AIConfig.module.css';

const PROVIDERS = [
  { value: 'ollama',     label: 'Ollama (local)' },
  { value: 'openai',    label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
];

const OLLAMA_MODELS   = ['kimi-k2.5:cloud', 'deepseek-coder-v2:lite', 'qwen2.5-coder:32b', 'llama3.1:8b'];
const OPENAI_MODELS   = ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'];
const ANTHROPIC_MODELS = ['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'];

function modelsFor(provider: string) {
  if (provider === 'openai')    return OPENAI_MODELS;
  if (provider === 'anthropic') return ANTHROPIC_MODELS;
  return OLLAMA_MODELS;
}

export default function AIConfigPage() {
  const { currentWorkspace } = useWorkspace();

  const [aiConfig, setAiConfig]       = useState<AIConfigOut | null>(null);
  const [aiLoading, setAiLoading]     = useState(false);
  const [aiProvider, setAiProvider]   = useState('ollama');
  const [aiModel, setAiModel]         = useState('');
  const [aiBaseUrl, setAiBaseUrl]     = useState('');
  const [aiApiKey, setAiApiKey]       = useState('');
  const [aiSaving, setAiSaving]       = useState(false);
  const [aiSaved, setAiSaved]         = useState(false);
  const [aiError, setAiError]         = useState('');
  const [testStatus, setTestStatus]   = useState<null | 'testing' | 'ok' | 'error'>(null);
  const [testDetail, setTestDetail]   = useState('');
  const [overrides, setOverrides]     = useState<Record<string, FeatureOverrideIn>>({});
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);

  useEffect(() => {
    if (!currentWorkspace) return;
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

  const handleSave = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;
    setAiError('');
    setAiSaving(true);
    try {
      const payload: AIConfigUpdate = {
        provider: aiProvider,
        model: aiModel,
        base_url: aiBaseUrl || undefined,
        api_key: aiApiKey || undefined,
        feature_overrides: Object.fromEntries(
          Object.entries(overrides).filter(([, v]) => v.provider || v.model || v.base_url || v.api_key)
        ),
      };
      const updated = await updateAIConfig(currentWorkspace.id, payload);
      setAiConfig(updated);
      setAiApiKey('');
      setAiSaved(true);
      setTimeout(() => setAiSaved(false), 2000);
    } catch (err: unknown) {
      setAiError(err instanceof Error ? err.message : 'Failed to save');
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
    setOverrides(prev => ({ ...prev, [feature]: { ...prev[feature], [field]: value } }));
  };

  if (!currentWorkspace) {
    return <main className={styles.container}><p className={styles.empty}>No workspace selected.</p></main>;
  }

  return (
    <main className={styles.container}>
      <h1 className={styles.title}>AI Configuration</h1>
      <p className={styles.subtitle}>
        Configure the AI model for <strong>{currentWorkspace.name}</strong>. Override per feature below.
      </p>

      {aiLoading ? (
        <p className={aiStyles.loading}>Loading…</p>
      ) : (
        <form className={aiStyles.form} onSubmit={handleSave}>

          {/* Default model */}
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
    </main>
  );
}
