/**
 * Character profile drawer (SA-63).
 * Shows full character details, appearance versions, LoRA model, and analytics.
 */
import { useState, useEffect, useRef } from 'react';
import type { Character, CharacterAnalytics } from '../api/characters';
import {
  updateCharacter, uploadVisualReference, addAppearanceVersion,
  setLoraModel, fetchCharacterAnalytics,
} from '../api/characters';
import { ROLE_LABELS } from '../api/characters';
import styles from './CharacterProfile.module.css';

interface Props {
  character: Character;
  onClose: () => void;
  onUpdate: (updated: Character) => void;
}

export function CharacterProfile({ character, onClose, onUpdate }: Props) {
  const [tab, setTab] = useState<'profile' | 'visual' | 'analytics'>('profile');
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    personality_prompt: character.personality_prompt ?? '',
    backstory: character.backstory ?? '',
    voice_profile_id: character.voice_profile_id ?? '',
  });
  const [analytics, setAnalytics] = useState<CharacterAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [versionLabel, setVersionLabel] = useState('');
  const [loraUrl, setLoraUrl] = useState(character.lora_model_url ?? '');
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (tab === 'analytics' && !analytics) {
      setAnalyticsLoading(true);
      fetchCharacterAnalytics(character.id)
        .then(setAnalytics)
        .catch(() => setAnalytics(null))
        .finally(() => setAnalyticsLoading(false));
    }
  }, [tab, analytics, character.id]);

  const saveProfile = async () => {
    setSaving(true);
    try {
      const updated = await updateCharacter(character.id, {
        personality_prompt: form.personality_prompt || undefined,
        backstory: form.backstory || undefined,
        voice_profile_id: form.voice_profile_id || undefined,
      });
      onUpdate(updated);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSaving(true);
    try {
      const updated = await uploadVisualReference(character.id, file);
      onUpdate(updated);
    } finally {
      setSaving(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleAddVersion = async () => {
    if (!versionLabel.trim()) return;
    setSaving(true);
    try {
      const updated = await addAppearanceVersion(character.id, { label: versionLabel.trim() });
      onUpdate(updated);
      setVersionLabel('');
    } finally {
      setSaving(false);
    }
  };

  const handleSetLora = async () => {
    if (!loraUrl.trim()) return;
    setSaving(true);
    try {
      const updated = await setLoraModel(character.id, loraUrl.trim());
      onUpdate(updated);
    } finally {
      setSaving(false);
    }
  };

  const versions = character.appearance_state?.versions ?? [];
  const refs = character.visual_references?.images ?? [];

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside className={styles.drawer}>
        <div className={styles.drawerHeader}>
          <div className={styles.avatarLg}>
            {character.name.split(' ').map(w => w[0]).join('').toUpperCase().slice(0, 2)}
          </div>
          <div>
            <h2 className={styles.drawerName}>{character.name}</h2>
            <span className={`${styles.roleBadge} ${styles[`role_${character.role_type}`]}`}>
              {ROLE_LABELS[character.role_type]}
            </span>
            {character.age != null && <span className={styles.ageMeta}> · Age {character.age}</span>}
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className={styles.tabs}>
          {(['profile', 'visual', 'analytics'] as const).map(t => (
            <button
              key={t}
              className={`${styles.tab} ${tab === t ? styles.activeTab : ''}`}
              onClick={() => setTab(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <div className={styles.body}>
          {tab === 'profile' && (
            <div className={styles.section}>
              {editing ? (
                <>
                  <label className={styles.label}>Personality Prompt</label>
                  <textarea
                    className={styles.textarea}
                    value={form.personality_prompt}
                    onChange={e => setForm(f => ({ ...f, personality_prompt: e.target.value }))}
                    rows={4}
                    placeholder="Describe how this character speaks and behaves…"
                  />
                  <label className={styles.label}>Backstory</label>
                  <textarea
                    className={styles.textarea}
                    value={form.backstory}
                    onChange={e => setForm(f => ({ ...f, backstory: e.target.value }))}
                    rows={4}
                    placeholder="Character backstory…"
                  />
                  <label className={styles.label}>Voice Profile ID</label>
                  <input
                    className={styles.input}
                    value={form.voice_profile_id}
                    onChange={e => setForm(f => ({ ...f, voice_profile_id: e.target.value }))}
                    placeholder="ElevenLabs voice ID…"
                  />
                  <div className={styles.editActions}>
                    <button className={styles.primaryBtn} onClick={saveProfile} disabled={saving}>
                      {saving ? 'Saving…' : 'Save'}
                    </button>
                    <button className={styles.ghostBtn} onClick={() => setEditing(false)}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Personality</span>
                    <p className={styles.fieldValue}>{character.personality_prompt || <em className={styles.empty}>Not set</em>}</p>
                  </div>
                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Backstory</span>
                    <p className={styles.fieldValue}>{character.backstory || <em className={styles.empty}>Not set</em>}</p>
                  </div>
                  <div className={styles.field}>
                    <span className={styles.fieldLabel}>Voice Profile</span>
                    <p className={styles.fieldValue}>{character.voice_profile_id || <em className={styles.empty}>Not linked</em>}</p>
                  </div>
                  <button className={styles.ghostBtn} onClick={() => setEditing(true)}>Edit Profile</button>
                </>
              )}
            </div>
          )}

          {tab === 'visual' && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>Reference Images</h3>
              {refs.length === 0 ? (
                <p className={styles.empty}>No reference images uploaded.</p>
              ) : (
                <div className={styles.refGrid}>
                  {refs.map((img, i) => (
                    <div key={i} className={styles.refItem}>
                      <div className={styles.refThumb}>📷</div>
                      <span className={styles.refName}>{img.filename}</span>
                    </div>
                  ))}
                </div>
              )}
              <input ref={fileRef} type="file" accept="image/*" className={styles.hidden} onChange={handleFileUpload} />
              <button className={styles.ghostBtn} onClick={() => fileRef.current?.click()} disabled={saving}>
                {saving ? 'Uploading…' : '+ Upload Reference Image'}
              </button>

              <h3 className={styles.sectionTitle} style={{ marginTop: '1.5rem' }}>Appearance Versions</h3>
              {versions.length === 0 ? (
                <p className={styles.empty}>No appearance versions saved.</p>
              ) : (
                <ul className={styles.versionList}>
                  {versions.map(v => (
                    <li key={v.id} className={`${styles.versionItem} ${character.appearance_state?.active_version_id === v.id ? styles.activeVersion : ''}`}>
                      <span className={styles.versionLabel}>{v.label}</span>
                      {character.appearance_state?.active_version_id === v.id && (
                        <span className={styles.activePill}>Active</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
              <div className={styles.inlineForm}>
                <input
                  className={styles.input}
                  placeholder="Version label (e.g. Season 2 look)"
                  value={versionLabel}
                  onChange={e => setVersionLabel(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAddVersion()}
                />
                <button className={styles.primaryBtn} onClick={handleAddVersion} disabled={saving || !versionLabel.trim()}>
                  Add
                </button>
              </div>

              <h3 className={styles.sectionTitle} style={{ marginTop: '1.5rem' }}>LoRA Model</h3>
              <p className={styles.fieldValue}>{character.lora_model_url || <em className={styles.empty}>No LoRA model linked</em>}</p>
              <div className={styles.inlineForm}>
                <input
                  className={styles.input}
                  placeholder="s3://bucket/models/character.safetensors"
                  value={loraUrl}
                  onChange={e => setLoraUrl(e.target.value)}
                />
                <button className={styles.primaryBtn} onClick={handleSetLora} disabled={saving || !loraUrl.trim()}>
                  Set
                </button>
              </div>
            </div>
          )}

          {tab === 'analytics' && (
            <div className={styles.section}>
              {analyticsLoading ? (
                <p className={styles.empty}>Loading analytics…</p>
              ) : analytics ? (
                <>
                  <div className={styles.statsGrid}>
                    <div className={styles.statCard}>
                      <span className={styles.statValue}>{analytics.total_appearances}</span>
                      <span className={styles.statLabel}>Appearances</span>
                    </div>
                    <div className={styles.statCard}>
                      <span className={styles.statValue}>{analytics.total_views.toLocaleString()}</span>
                      <span className={styles.statLabel}>Total Views</span>
                    </div>
                    <div className={styles.statCard}>
                      <span className={styles.statValue}>{Math.round(analytics.avg_views_per_appearance).toLocaleString()}</span>
                      <span className={styles.statLabel}>Avg Views / Appearance</span>
                    </div>
                  </div>

                  {Object.keys(analytics.engagement_breakdown).length > 0 && (
                    <>
                      <h3 className={styles.sectionTitle}>Views by Project</h3>
                      <ul className={styles.breakdownList}>
                        {Object.entries(analytics.engagement_breakdown)
                          .sort(([, a], [, b]) => b - a)
                          .map(([pid, views]) => (
                            <li key={pid} className={styles.breakdownItem}>
                              <span className={styles.breakdownId}>{pid.slice(0, 8)}…</span>
                              <span className={styles.breakdownViews}>{views.toLocaleString()} views</span>
                            </li>
                          ))}
                      </ul>
                    </>
                  )}
                </>
              ) : (
                <p className={styles.empty}>No analytics data available yet.</p>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
