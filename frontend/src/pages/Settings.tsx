import { useState, useEffect, FormEvent } from 'react';
import { useWorkspace } from '../context/WorkspaceContext';
import { apiClient } from '../api/client';
import styles from './Settings.module.css';

export default function Settings() {
  const { currentWorkspace, refreshWorkspaces } = useWorkspace();
  const [name, setName] = useState('');
  const [styleGuide, setStyleGuide] = useState('');
  const [competitorChannels, setCompetitorChannels] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!currentWorkspace) return;
    setName(currentWorkspace.name);
    setStyleGuide(currentWorkspace.style_guide ? JSON.stringify(currentWorkspace.style_guide, null, 2) : '');
    setCompetitorChannels((currentWorkspace.competitor_channels ?? []).join(', '));
  }, [currentWorkspace]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!currentWorkspace) return;
    setError('');
    setSaving(true);
    try {
      let parsedStyle = null;
      if (styleGuide.trim()) parsedStyle = JSON.parse(styleGuide);
      await apiClient.put(`/workspaces/${currentWorkspace.id}`, {
        name,
        style_guide: parsedStyle,
        competitor_channels: competitorChannels
          ? competitorChannels.split(',').map((s) => s.trim()).filter(Boolean)
          : null,
      });
      await refreshWorkspaces();
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleYouTubeConnect = () => {
    if (!currentWorkspace) return;
    window.location.href = `${import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}/workspaces/${currentWorkspace.id}/youtube/connect`;
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

      <form className={styles.form} onSubmit={handleSubmit}>
        <div className={styles.field}>
          <label className={styles.label}>Workspace name</label>
          <input className={styles.input} value={name} onChange={(e) => setName(e.target.value)} required />
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

        <div className={styles.field}>
          <label className={styles.label}>Style guide (JSON)</label>
          <textarea className={styles.textarea} value={styleGuide} onChange={(e) => setStyleGuide(e.target.value)} placeholder='{"tone": "casual", "language": "en"}' rows={3} />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Competitor channels (comma-separated)</label>
          <input className={styles.input} value={competitorChannels} onChange={(e) => setCompetitorChannels(e.target.value)} placeholder="UCxxxxxx, UCyyyyyy" />
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <button type="submit" className={styles.saveButton} disabled={saving}>
          {saving ? 'Saving…' : saved ? 'Saved ✓' : 'Save changes'}
        </button>
      </form>
    </main>
  );
}
